# simulator.py
"""
Módulo de simulação: orquestra a execução do algoritmo de Tomasulo.
"""
from core import Instruction, RegisterFile, ReservationStation, ReorderBuffer, ROBEntry, BranchPredictor

class TomasuloSimulator:
    """Simulador do algoritmo de Tomasulo."""
    def __init__(self):
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

    def step(self):
        if self.halted or self.finished:
            return
        self.cycle += 1
        self.commit()
        self.write_back()
        self.execute()
        self.dispatch()

    def dispatch(self):
        # Emissão múltipla: tenta emitir o máximo possível de instruções independentes
        issued = 0
        max_issue = len(self.reservation_stations)  # Limite prático: tantas quanto RS livres
        while self.pc < len(self.instructions) and issued < max_issue:
            instr = self.instructions[self.pc]
            if instr.opcode == 'HLT':
                self.halted = True
                break
            # Procura RS livre
            rs = self.find_free_rs(instr)
            if not rs or self.rob.is_full():
                self.stalls += 1
                break  # Não há mais espaço para emitir neste ciclo
            # Checa dependências (RAW, WAW, WAR)
            if not self.can_issue(instr):
                break  # Não pode emitir por dependência
            # Aloca ROB
            rob_idx = len(self.rob)
            rob_entry = ROBEntry(rob_idx, instr, instr.rd if instr.opcode not in ['SD', 'STORE'] else None)
            self.rob.add(rob_entry)
            # Preenche RS
            rs.busy = True
            rs.op = instr.opcode
            rs.instr = instr
            rs.rob_idx = rob_idx
            rs.dest = rob_idx
            # Dependências
            if instr.opcode in {'ADD', 'SUB', 'MUL', 'DIV'}:
                rs.Vj, rs.Qj = self.get_operand(instr.rs)
                rs.Vk, rs.Qk = self.get_operand(instr.rt)
                self.register_file.set_tag(instr.rd, rob_idx)
                rs.exec_cycles = self.get_latency(instr.opcode)
                rs.remaining = rs.exec_cycles
            elif instr.opcode in {'ADDI', 'SUBI'}:
                rs.Vj, rs.Qj = self.get_operand(instr.rs)
                rs.Vk = int(instr.imm)
                rs.Qk = None
                self.register_file.set_tag(instr.rd, rob_idx)
                rs.exec_cycles = self.get_latency(instr.opcode)
                rs.remaining = rs.exec_cycles
            elif instr.opcode == 'LD':
                base, qbase = self.get_operand(instr.rs)
                offset = int(instr.imm) if instr.imm is not None else 0
                if qbase is None:
                    addr = base + offset
                    rs.Vj = addr
                    rs.Qj = None
                else:
                    rs.Vj = None
                    rs.Qj = qbase
                rs.Vk = None
                rs.Qk = None
                self.register_file.set_tag(instr.rd, rob_idx)
                rs.exec_cycles = self.get_latency('LD')
                rs.remaining = rs.exec_cycles
            elif instr.opcode == 'SD':
                base, qbase = self.get_operand(instr.rs)
                offset = int(instr.imm) if instr.imm is not None else 0
                if qbase is None:
                    addr = base + offset
                    rs.Vj = addr
                    rs.Qj = None
                else:
                    rs.Vj = None
                    rs.Qj = qbase
                rs.Vk, rs.Qk = self.get_operand(instr.rd)
                rs.exec_cycles = self.get_latency('SD')
                rs.remaining = rs.exec_cycles
            elif instr.opcode in {'BNE', 'BNEZ'}:
                rs.Vj, rs.Qj = self.get_operand(instr.rs)
                if instr.opcode == 'BNE':
                    rs.Vk, rs.Qk = self.get_operand(instr.rt)
                else:
                    rs.Vk = None
                    rs.Qk = None
                rs.exec_cycles = 1
                rs.remaining = 1
            else:
                pass
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

    def get_operand(self, reg):
        if reg is None:
            return None, None
        tag = self.register_file.get_tag(reg)
        if tag is None:
            return self.register_file.get(reg), None
        else:
            return None, tag

    def find_free_rs(self, instr):
        opmap = {
            'ADD': 'ADD', 'SUB': 'ADD', 'ADDI': 'ADD', 'SUBI': 'ADD',
            'MUL': 'MUL', 'DIV': 'MUL',
            'LD': 'LOAD', 'SD': 'STORE',
            'BNE': 'BRANCH', 'BNEZ': 'BRANCH'
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
            return 2
        elif op in {'BNE', 'BNEZ'}:
            return 1
        return 1

    def execute(self):
        # 1. Libera UFs cujas RS terminaram execução
        for t, uflist in self.functional_units.items():
            for uf in uflist:
                rs = uf['rs']
                if rs and rs.busy and rs.remaining == 0:
                    uf['rs'] = None
                    uf['busy'] = False
        # 2. Para cada tipo de UF, aloque RSs prontas para execução
        for t, uflist in self.functional_units.items():
            # RSs desse tipo que estão ocupadas, prontas, mas ainda não executando
            rs_candidates = [rs for rs in self.reservation_stations if rs.op_type == t and rs.busy and rs.remaining > 0 and not any(uf['rs'] == rs for uf in uflist) and rs.Qj is None and rs.Qk is None]
            for rs in rs_candidates:
                # Procura UF livre
                for uf in uflist:
                    if not uf['busy']:
                        uf['rs'] = rs
                        uf['busy'] = True
                        break
        # 3. Para cada UF ocupada, execute 1 ciclo
        for t, uflist in self.functional_units.items():
            for uf in uflist:
                rs = uf['rs']
                if rs and rs.busy and rs.remaining > 0:
                    rs.remaining -= 1
                    if rs.remaining == 0:
                        self.waiting_wb.append(rs)
        # 4. Propaga valores do CDB (simples)
        for rs in self.reservation_stations:
            if rs.busy:
                if rs.Qj is not None:
                    rob_entry = self.rob[rs.Qj] if rs.Qj < len(self.rob) else None
                    if rob_entry and rob_entry.ready:
                        rs.Vj = rob_entry.value
                        rs.Qj = None
                if rs.Qk is not None:
                    rob_entry = self.rob[rs.Qk] if rs.Qk < len(self.rob) else None
                    if rob_entry and rob_entry.ready:
                        rs.Vk = rob_entry.value
                        rs.Qk = None

    def write_back(self):
        # WB para RS prontos
        for rs in list(self.waiting_wb):
            if not rs.busy:
                continue
            instr = rs.instr
            rob_entry = self.rob[rs.rob_idx]
            if instr.opcode in {'ADD', 'SUB', 'ADDI', 'SUBI'}:
                vj = rs.Vj
                vk = rs.Vk
                if instr.opcode in {'ADD', 'ADDI'}:
                    result = vj + vk
                else:
                    result = vj - vk
                rob_entry.value = result
                rob_entry.ready = True
            elif instr.opcode in {'MUL', 'DIV'}:
                vj = rs.Vj
                vk = rs.Vk
                if instr.opcode == 'MUL':
                    result = vj * vk
                else:
                    result = vj / vk if vk != 0 else 0
                rob_entry.value = result
                rob_entry.ready = True
            elif instr.opcode == 'LD':
                addr = rs.Vj
                rob_entry.value = self.memory.get(addr, 0.0)
                rob_entry.ready = True
            elif instr.opcode == 'SD':
                # Store: valor será escrito no commit
                rob_entry.value = (rs.Vj, rs.Vk)
                rob_entry.ready = True
            elif instr.opcode in {'BNE', 'BNEZ'}:
                # Predição e resultado real
                taken = False
                if instr.opcode == 'BNE':
                    taken = (rs.Vj != rs.Vk)
                else:
                    taken = (rs.Vj != 0)
                predicted = self.branch_predictor.predict(instr)
                self.branch_predictor.update(taken, predicted)
                rob_entry.value = taken
                rob_entry.ready = True
                rob_entry.mispredicted = (taken != predicted)
            rs.ready = True
            self.waiting_wb.remove(rs)

    def commit(self):
        # Commit múltiplo: enquanto houver instrução pronta no início do ROB
        while self.rob.entries:
            rob_entry = self.rob.entries[0]
            instr = rob_entry.instr
            if not rob_entry.ready:
                break
            if instr.opcode in {'ADD', 'SUB', 'MUL', 'DIV', 'ADDI', 'SUBI', 'LD'}:
                # Escreve no registrador destino
                if self.register_file.get_tag(instr.rd) == rob_entry.idx:
                    self.register_file.set(instr.rd, rob_entry.value)
                    self.register_file.clear_tag(instr.rd)
                self.committed += 1
            elif instr.opcode == 'SD':
                addr, value = rob_entry.value
                self.memory[addr] = value
                self.committed += 1
            elif instr.opcode in {'BNE', 'BNEZ'}:
                if rob_entry.mispredicted:
                    # Flush pipeline (didático: limpa RS e ROB)
                    self.flush_pipeline()
                    # Corrige PC
                    if rob_entry.value:
                        self.pc = self.labels.get(instr.target, self.pc)
                    else:
                        self.pc += 1
                self.committed += 1
            self.rob.remove()
            # Libera RS correspondente
            for rs in self.reservation_stations:
                if rs.rob_idx == rob_entry.idx:
                    rs.clear()
            # Fim do programa
            if instr.opcode == 'HLT' or self.pc >= len(self.instructions):
                self.finished = True
                break

    def flush_pipeline(self):
        for rs in self.reservation_stations:
            rs.clear()
        self.rob = ReorderBuffer(size=16)
        self.waiting_wb = []

    def get_state(self):
        # Estado para GUI
        return {
            'RS': '\n'.join(str(rs) for rs in self.reservation_stations),
            'ROB': self.rob.dump(),
            'REGS': self.register_file.dump(),
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

    def get_state(self):
        # Estado para GUI
        return {
            'RS': '\n'.join(str(rs) for rs in self.reservation_stations),
            'ROB': self.rob.dump(),
            'REGS': self.register_file.dump(),
        }

    def get_metrics(self):
        return {
            'IPC': round(self.committed / self.cycle, 2) if self.cycle else 0,
            'Ciclos': self.cycle,
            'Stalls': self.stalls,
            'Taxa de acerto de desvio': f'{self.branch_predictor.accuracy()*100:.1f}%'
        } 