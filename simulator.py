# simulator.py
"""
Módulo de simulação: orquestra a execução do algoritmo de Tomasulo.
"""
from core import Instruction, RegisterFile, ReservationStation, ReorderBuffer, ROBEntry, BranchPredictor
from typing import Optional, Union, Tuple

class TomasuloSimulator:
    """Simulador do algoritmo de Tomasulo."""
    def __init__(self, issue_width=4):
        self.issue_width = issue_width
        self.instructions = []  # Lista de Instruction
        self.labels = {}        # label -> idx
        self.pc = 0            # índice da próxima instrução
        self.finished = False
        self.register_file = RegisterFile()
        # 3 RS para cada tipo (didático)
        self.reservation_stations = [
            ReservationStation(f'ADD{i}', 'ADD') for i in range(3)
        ] + [
            ReservationStation(f'MUL{i}', 'MUL') for i in range(2)
        ] + [
            ReservationStation(f'LOAD{i}', 'LOAD') for i in range(2)
        ] + [
            ReservationStation(f'STORE{i}', 'STORE') for i in range(2)
        ] + [
            ReservationStation(f'BR{i}', 'BRANCH') for i in range(1)
        ]
        self.rob = ReorderBuffer(size=16)
        self.branch_predictor = BranchPredictor()
        self.cycle = 0
        self.stalls = 0
        self.committed = 0
        self.memory = {i: 1.0 for i in range(0, 128, 8)}  # Memória didática
        self.executing = []  # RS em execução
        self.waiting_wb = [] # RS prontos para WB
        self.halted = False
        # --- Unidades Funcionais ---
        self.functional_units = {
            'ADD': [{'rs': None, 'busy': False} for _ in range(2)],
            'MUL': [{'rs': None, 'busy': False} for _ in range(2)],
            'LOAD': [{'rs': None, 'busy': False} for _ in range(2)],
            'STORE': [{'rs': None, 'busy': False} for _ in range(2)],
            'BRANCH': [{'rs': None, 'busy': False} for _ in range(1)],
        }
        self.cycle_log = []

    def load_instructions(self, lines):
        self.instructions = []
        self.labels = {}
        for idx, line in enumerate(lines):
            instr = Instruction(line)
            if instr.label:
                self.labels[instr.label] = len(self.instructions)
            if instr.opcode:
                self.instructions.append(instr)
        self.pc = 0
        self.finished = False
        self.reset_state()

    def reset_state(self):
        self.register_file = RegisterFile()
        self.rob = ReorderBuffer(size=16)
        self.branch_predictor = BranchPredictor()
        for rs in self.reservation_stations:
            rs.clear()
        self.cycle = 0
        self.stalls = 0
        self.committed = 0
        self.executing = []
        self.waiting_wb = []
        self.halted = False
        self.memory = {i: 1.0 for i in range(0, 128, 8)}
        # Limpa UFs
        for uflist in self.functional_units.values():
            for uf in uflist:
                uf['rs'] = None
                uf['busy'] = False
        self.cycle_log.clear()

    def step(self):
        if self.finished:
            return
        self.cycle_log.clear()
        self.cycle += 1
        self.commit()
        self.write_back()
        self.execute()
        self.dispatch()

    def dispatch(self):
        # Para a emissão se a instrução HLT já foi emitida
        if self.halted:
            return

        # Emissão superescalar: tenta emitir até `issue_width` instruções por ciclo
        issued = 0
        while issued < self.issue_width and self.pc < len(self.instructions):
            instr = self.instructions[self.pc]

            if instr.opcode == 'HLT':
                self.halted = True
                self.cycle_log.append("DISPATCH: Instrução HLT encontrada. Parando a emissão.")
                break

            # Procura RS livre
            rs = self.find_free_rs(instr)
            if not rs or self.rob.is_full():
                self.stalls += 1
                self.cycle_log.append(f"DISPATCH: Stall - Nenhuma RS ou ROB livre para '{instr.opcode}'.")
                break  # Bloqueio estrutural

            # Aloca entrada no ROB
            rob_idx = self.rob.get_next_id()
            rob_entry = ROBEntry(rob_idx, instr, instr.rd if instr.opcode not in ['SD'] else None)
            self.rob.add(rob_entry)
            self.cycle_log.append(f"DISPATCH: '{instr}' emitida para {rs.name} e ROB ID {rob_idx}.")

            # Preenche a Estação de Reserva
            rs.busy = True
            rs.op = instr.opcode
            rs.instr = instr
            rs.rob_idx = rob_idx
            rs.dest = rob_idx # O destino é a entrada do ROB

            # Busca operandos e configura dependências
            if instr.opcode in {'ADD', 'SUB', 'MUL', 'DIV'}:
                rs.Vj, rs.Qj = self.get_operand(instr.rs)
                rs.Vk, rs.Qk = self.get_operand(instr.rt)
                if instr.rd:
                    self.register_file.set_tag(instr.rd, rob_idx)
                rs.exec_cycles = self.get_latency(instr.opcode)
            elif instr.opcode in {'ADDI', 'SUBI'}:
                rs.Vj, rs.Qj = self.get_operand(instr.rs)
                rs.Vk = int(instr.imm) if instr.imm else 0
                rs.Qk = None
                if instr.rd:
                    self.register_file.set_tag(instr.rd, rob_idx)
                rs.exec_cycles = self.get_latency(instr.opcode)
            elif instr.opcode == 'LD':
                base, qbase = self.get_operand(instr.rs)
                offset = int(instr.imm) if instr.imm is not None else 0
                if qbase is None and isinstance(base, (int, float)):
                    rob_entry.address = int(base + offset)
                    rob_entry.address_ready = True
                else:
                    rs.Qj = qbase # Dependência para cálculo de endereço
                rs.Vj = offset # Guarda o offset
                if instr.rd:
                    self.register_file.set_tag(instr.rd, rob_idx)
                rs.exec_cycles = self.get_latency('LD')
            elif instr.opcode == 'SD':
                # Endereço
                base, qbase = self.get_operand(instr.rs)
                offset = int(instr.imm) if instr.imm is not None else 0
                if qbase is None and isinstance(base, (int, float)):
                    rob_entry.address = int(base + offset)
                    rob_entry.address_ready = True
                else:
                    rs.Qj = qbase # Dependência para cálculo de endereço
                rs.Vj = offset
                # Valor a ser escrito
                rs.Vk, rs.Qk = self.get_operand(instr.rd) # Em SD, rd é a fonte do valor
                rs.exec_cycles = self.get_latency('SD')
            elif instr.opcode in {'BNE', 'BNEZ', 'BEQ'}:
                rs.Vj, rs.Qj = self.get_operand(instr.rs)
                if instr.opcode == 'BNEZ':
                    rs.Vk, rs.Qk = 0, None # BNEZ compara com zero
                else: # BEQ, BNE
                    rs.Vk, rs.Qk = self.get_operand(instr.rt)
                rs.exec_cycles = self.get_latency('BRANCH')

            rs.remaining = rs.exec_cycles
            self.pc += 1
            issued += 1

    def can_issue(self, instr):
        # Checa dependências RAW, WAW, WAR para a instrução
        # RAW: algum operando depende de instrução ainda não emitida
        # WAW: destino já está marcado para escrita por outra instrução no ROB
        # WAR: algum operando será sobrescrito por instrução ainda não emitida
        # Para simplificação, só checa registradores
        if instr.opcode in {'ADD', 'SUB', 'MUL', 'DIV', 'ADDI', 'SUBI', 'LD'}:
            # RAW
            for reg in [instr.rs, instr.rt]:
                if reg and self.register_file.get_tag(reg) is not None:
                    return False
            # WAW
            if instr.rd and self.register_file.get_tag(instr.rd) is not None:
                return False
        elif instr.opcode == 'SD':
            # RAW
            if instr.rd and self.register_file.get_tag(instr.rd) is not None:
                return False
            if instr.rs and self.register_file.get_tag(instr.rs) is not None:
                return False
        elif instr.opcode in {'BNE', 'BNEZ'}:
            if instr.rs and self.register_file.get_tag(instr.rs) is not None:
                return False
            if hasattr(instr, 'rt') and instr.rt and self.register_file.get_tag(instr.rt) is not None:
                return False
        return True

    def get_operand(self, reg: Optional[str]) -> Tuple[Optional[Union[int, float]], Optional[int]]:
        if reg is None:
            return None, None
        
        tag = self.register_file.get_tag(reg)
        if tag is None:
            val = self.register_file.get(reg)
            return val, None
        
        # Dependência: verifica se o valor já está pronto no ROB
        rob_entry = self.rob[tag]
        # Apenas resultados numéricos (de self.result) são propagados pelo CDB
        if rob_entry and rob_entry.ready:
            return rob_entry.result, None
        else:
            return None, tag

    def find_free_rs(self, instr):
        opmap = {
            'ADD': 'ADD', 'SUB': 'ADD', 'ADDI': 'ADD', 'SUBI': 'ADD',
            'MUL': 'MUL', 'DIV': 'MUL',
            'LD': 'LOAD', 'SD': 'STORE',
            'BNE': 'BRANCH', 'BNEZ': 'BRANCH', 'BEQ': 'BRANCH'
        }
        t = opmap.get(instr.opcode)
        for rs in self.reservation_stations:
            if rs.op_type == t and not rs.busy:
                return rs
        return None

    def get_latency(self, op):
        # Latências conforme solicitado
        if op in {'ADD', 'SUB', 'ADDI', 'SUBI'}:
            return 1
        elif op in {'MUL', 'DIV'}:
            return 2
        elif op == 'LD':
            return 2
        elif op == 'SD':
            return 1 # Apenas para cálculo do endereço
        elif op in {'BNE', 'BNEZ', 'BRANCH'}:
            return 1
        return 1

    def execute(self):
        # 1. Libera UFs que terminaram
        for uflist in self.functional_units.values():
            for uf in uflist:
                if uf['rs'] and uf['rs'].remaining == 0:
                    self.cycle_log.append(f"EXECUTE: '{uf['rs'].instr}' terminou a execução.")
                    uf['rs'] = None
                    uf['busy'] = False
        
        # 2. Inicia execução em RSs prontas
        for t, uflist in self.functional_units.items():
            # Candidatos: RSs ocupadas, com operandos prontos, ainda não executando
            rs_candidates = [
                rs for rs in self.reservation_stations 
                if rs.op_type == t and rs.busy and rs.remaining > 0 and 
                   rs.Qj is None and rs.Qk is None and
                   not any(uf['rs'] == rs for uf in uflist)
            ]
            
            # Para LD/SD, o endereço deve estar pronto
            if t == 'LOAD' or t == 'STORE':
                def is_addr_ready(rs):
                    if rs.rob_idx is None: return False
                    entry = self.rob[rs.rob_idx]
                    return entry is not None and entry.address_ready
                rs_candidates = [rs for rs in rs_candidates if is_addr_ready(rs)]

            for rs in rs_candidates:
                # Procura UF livre
                for uf in uflist:
                    if not uf['busy']:
                        uf['rs'] = rs
                        uf['busy'] = True
                        self.cycle_log.append(f"EXECUTE: '{rs.instr}' começou a execução na unidade {t}.")
                        break
        
        # 3. Decrementa ciclo de execução para RSs em UFs
        for uflist in self.functional_units.values():
            for uf in uflist:
                rs = uf['rs']
                if rs and rs.busy and rs.remaining > 0:
                    rs.remaining -= 1
                    if rs.remaining == 0:
                        self.waiting_wb.append(rs)

    def write_back(self):
        # Propaga resultados pelo CDB para as RS e ROB
        for rs_done in list(self.waiting_wb):
            if not rs_done.busy or rs_done.rob_idx is None:
                continue
            
            rob_entry = self.rob[rs_done.rob_idx]
            if rob_entry is None:  # A entrada do ROB pode ter sido removida por um flush
                rs_done.clear()
                self.waiting_wb.remove(rs_done)
                continue

            result = None
            vj = rs_done.Vj
            vk = rs_done.Vk

            # Calcula o resultado
            if rs_done.op in {'ADD', 'SUB', 'ADDI', 'SUBI'}:
                if isinstance(vj, (int, float)) and isinstance(vk, (int, float)):
                    result = vj + vk if rs_done.op in {'ADD', 'ADDI'} else vj - vk
            elif rs_done.op in {'MUL', 'DIV'}:
                if isinstance(vj, (int, float)) and isinstance(vk, (int, float)):
                    result = vj * vk if rs_done.op == 'MUL' else (vj / vk if vk != 0 else 0)
            elif rs_done.op == 'LD':
                addr = rob_entry.address
                if addr is not None:
                    result = self.memory.get(addr, 0.0)
                    self.cycle_log.append(f"WRITE-BACK: LD para ROB {rob_entry.idx} leu o valor {result} do endereço {addr}.")
            elif rs_done.op == 'SD':
                # O valor a ser armazenado já está na RS (Vk) e o endereço no ROB
                rob_entry.store_value = vk 
                rob_entry.ready = True # SD está pronto para o commit
                self.cycle_log.append(f"WRITE-BACK: SD para ROB {rob_entry.idx} está pronto para commit.")
                rs_done.ready = True
                self.waiting_wb.remove(rs_done)
                continue # SD não escreve no CDB
            elif rs_done.op in {'BNE', 'BNEZ', 'BEQ'}:
                taken = False
                vj = rs_done.Vj
                vk = rs_done.Vk
                
                # Garante que os valores não sejam None antes de comparar
                if vj is not None and vk is not None:
                    if rs_done.op == 'BEQ':
                        taken = (vj == vk)
                    elif rs_done.op == 'BNE':
                        taken = (vj != vk)
                    elif rs_done.op == 'BNEZ':
                        taken = (vj != 0)

                predicted = self.branch_predictor.predict(rs_done.instr)
                self.branch_predictor.update(taken, predicted)
                target_addr = self.labels.get(rs_done.instr.target) if rs_done.instr.target else None
                rob_entry.branch_outcome = (taken, target_addr)
                rob_entry.mispredicted = (taken != predicted)
                rob_entry.ready = True
                self.cycle_log.append(f"WRITE-BACK: Branch no ROB {rob_entry.idx} resolvido. Desvio: {taken}.")
                rs_done.ready = True
                self.waiting_wb.remove(rs_done)
                continue # Branch não escreve no CDB
            
            # Atualiza ROB
            rob_entry.result = result
            rob_entry.ready = True
            
            # Transmite no CDB: atualiza outras RS
            # Apenas resultados numéricos são transmitidos
            if result is not None:
                self.cycle_log.append(f"WRITE-BACK: ROB {rob_entry.idx} transmitiu o resultado {result:.2f} no CDB.")
                tag = rs_done.rob_idx
                for rs in self.reservation_stations:
                    if rs.Qj == tag:
                        rs.Vj = result
                        rs.Qj = None
                    if rs.Qk == tag:
                        rs.Vk = result
                        rs.Qk = None
                
                # Atualiza dependências de endereço em LD/SD
                for entry in self.rob.entries:
                    if not entry.address_ready:
                        # Checa se alguma RS esperando por este resultado pode calcular endereço
                        rs_mem = next((rs for rs in self.reservation_stations if rs.rob_idx == entry.idx), None)
                        if rs_mem and rs_mem.Qj == tag and isinstance(result, (int, float)) and isinstance(rs_mem.Vj, (int, float)):
                            entry.address = int(result + rs_mem.Vj) # base + offset
                            entry.address_ready = True
                            rs_mem.Qj = None

            rs_done.ready = True
            self.waiting_wb.remove(rs_done)

    def commit(self):
        # Commit em ordem do ROB
        commit_count = 0
        while commit_count < self.issue_width and self.rob.entries and self.rob.entries[0].ready:
            rob_entry = self.rob.entries[0]
            instr = rob_entry.instr

            if rob_entry.mispredicted:
                outcome = rob_entry.branch_outcome
                if outcome:
                    taken, target_pc = outcome
                    try:
                        instr_idx = self.instructions.index(instr)
                        return_pc = instr_idx + 1
                    except ValueError:
                        return_pc = self.pc

                    if target_pc is not None:
                        # Log centralizado que dispara o flush
                        self.cycle_log.append(f"COMMIT: Desvio mal previsto em '{instr}' (ROB ID {rob_entry.idx}). Iniciando flush.")
                        self.flush_pipeline(new_pc=target_pc if taken else return_pc)
                    
                    break # Flush interrompe commit no ciclo

            if instr.opcode in {'ADD', 'SUB', 'MUL', 'DIV', 'ADDI', 'SUBI', 'LD'}:
                if rob_entry.dest and self.register_file.get_tag(rob_entry.dest) == rob_entry.idx:
                    self.register_file.set(rob_entry.dest, rob_entry.result)
                    self.register_file.clear_tag(rob_entry.dest)
                self.cycle_log.append(f"COMMIT: Instrução '{instr}' (ROB {rob_entry.idx}) finalizada.")
            elif instr.opcode == 'SD':
                if rob_entry.address is not None and rob_entry.store_value is not None:
                    self.memory[rob_entry.address] = float(rob_entry.store_value)
                self.cycle_log.append(f"COMMIT: Store '{instr}' (ROB {rob_entry.idx}) finalizado.")
            elif instr.opcode in {'BNE', 'BNEZ'}:
                self.cycle_log.append(f"COMMIT: Desvio '{instr}' (ROB {rob_entry.idx}) finalizado.")
                pass # Tratado na misprediction
            
            # Libera RS e ROB
            self.rob.remove()
            for rs in self.reservation_stations:
                if rs.rob_idx == rob_entry.idx:
                    rs.clear()
                    break
            
            self.committed += 1
            commit_count += 1
            
            # Fim do programa
            if self.pc >= len(self.instructions) and len(self.rob) == 0:
                self.finished = True
                break
    
    def flush_pipeline(self, new_pc):
        # Log das instruções que serão descartadas
        for entry in self.rob.entries:
            self.cycle_log.append(f"  -> FLUSH: Descartando '{entry.instr}' (ROB ID {entry.idx}).")
            
        # Limpa RS, ROB, e itens em voo. Ajusta o PC.
        for rs in self.reservation_stations:
            rs.clear()
        for tag in self.register_file.int_tags: self.register_file.clear_tag(tag)
        for tag in self.register_file.fp_tags: self.register_file.clear_tag(tag)

        self.rob.clear()
        self.waiting_wb.clear()
        self.pc = new_pc
        self.halted = False # Permite que a emissão recomece do caminho correto
        # Limpa UFs também
        for uflist in self.functional_units.values():
            for uf in uflist:
                uf['rs'] = None
                uf['busy'] = False

    def get_state(self):
        # Estado para GUI
        return {
            'RS': '\n'.join(str(rs) for rs in self.reservation_stations),
            'ROB': self.rob.dump(),
            'REGS': self.register_file.dump(),
            'LOG': self.cycle_log,
        }

    def get_metrics(self):
        return {
            'IPC': round(self.committed / self.cycle, 2) if self.cycle else 0,
            'Ciclos': self.cycle,
            'Stalls': self.stalls,
            'Taxa de acerto de desvio': f'{self.branch_predictor.accuracy()*100:.1f}%'
        }

    def reset(self):
        self.reset_state() 