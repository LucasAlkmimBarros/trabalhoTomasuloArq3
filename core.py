# core.py
"""
Módulo central: estruturas de dados e lógica do algoritmo de Tomasulo.
Inclui: instrução, registradores, estações de reserva, ROB, preditor de desvio.
"""

import re
from typing import Optional, Union, Tuple

class Instruction:
    """Representa uma instrução MIPS simplificada."""
    def __init__(self, raw_text):
        self.raw_text = raw_text.strip()
        self.label = None
        self.opcode = None
        self.rd = None
        self.rs = None
        self.rt = None
        self.imm = None
        self.target = None
        self.parse()

    def parse(self):
        line = self.raw_text
        # Remove comentários
        line = line.split('#')[0].strip()
        if not line:
            return
        # Label
        if ':' in line:
            self.label, line = [x.strip() for x in line.split(':', 1)]
        # Tokenização
        tokens = re.split(r'[ ,()]+', line)
        if not tokens or not tokens[0]:
            return
        self.opcode = tokens[0].upper()
        if self.opcode == 'LW':
            self.opcode = 'LD'
        elif self.opcode == 'SW':
            self.opcode = 'SD'
        # Formatos suportados
        if self.opcode in {'ADD', 'SUB', 'MUL', 'DIV'}:
            # ADD rd, rs, rt
            self.rd, self.rs, self.rt = tokens[1:4]
        elif self.opcode in {'ADDI', 'SUBI'}:
            # ADDI rd, rs, imm
            self.rd, self.rs, self.imm = tokens[1:4]
        elif self.opcode in {'LD', 'SD'}:
            self.rd = tokens[1] if len(tokens) > 1 else None
            if len(tokens) >= 4:
                self.imm = tokens[2] if tokens[2] else '0'
                self.rs = tokens[3]
            elif len(tokens) == 3:
                self.imm = '0'
                self.rs = tokens[2]
            else:
                self.imm = '0'
                self.rs = None
        elif self.opcode in {'BNE', 'BEQ'}:
            # BNE rs, rt, label
            self.rs, self.rt, self.target = tokens[1:4]
        elif self.opcode == 'BNEZ':
            # BNEZ rs, label
            self.rs, self.target = tokens[1:3]
        elif self.opcode == 'HLT':
            pass
        else:
            # Não suportado
            pass

    def __repr__(self):
        return f"{self.raw_text}"

class RegisterFile:
    """Tabela de registradores inteiros e float."""
    def __init__(self):
        self.int_regs = {f'R{i}': 0 for i in range(32)}
        self.fp_regs = {f'F{i}': 0.0 for i in range(32)}
        # Para Tomasulo: cada reg tem um campo 'Qi' (tag do produtor)
        self.int_tags = {f'R{i}': None for i in range(32)}
        self.fp_tags = {f'F{i}': None for i in range(32)}

    def get(self, reg):
        if reg.startswith('R'):
            return self.int_regs[reg]
        elif reg.startswith('F'):
            return self.fp_regs[reg]
        else:
            raise ValueError(f'Registro inválido: {reg}')

    def set(self, reg, value):
        if reg.startswith('R'):
            self.int_regs[reg] = value
        elif reg.startswith('F'):
            self.fp_regs[reg] = value
        else:
            raise ValueError(f'Registro inválido: {reg}')

    def get_tag(self, reg):
        if reg.startswith('R'):
            return self.int_tags[reg]
        elif reg.startswith('F'):
            return self.fp_tags[reg]
        else:
            raise ValueError(f'Registro inválido: {reg}')

    def set_tag(self, reg, tag):
        if reg.startswith('R'):
            self.int_tags[reg] = tag
        elif reg.startswith('F'):
            self.fp_tags[reg] = tag
        else:
            raise ValueError(f'Registro inválido: {reg}')

    def clear_tag(self, reg):
        self.set_tag(reg, None)

    def dump(self):
        s = 'Inteiros:\n' + ' '.join(f'{k}:{v}' for k, v in self.int_regs.items() if v != 0)
        s += '\nFP:      ' + ' '.join(f'{k}:{v:.2f}' for k, v in self.fp_regs.items() if v != 0)
        return s if s.strip() else 'Todos zero.'

class ReservationStation:
    """Estação de reserva genérica."""
    def __init__(self, name, op_type):
        self.name: str = name
        self.op_type: str = op_type  # 'ADD', 'MUL', 'LOAD', 'STORE', 'BRANCH'
        self.busy: bool = False
        self.op: Optional[str] = None
        self.Vj: Optional[Union[int, float]] = None
        self.Vk: Optional[Union[int, float]] = None
        self.Qj: Optional[int] = None
        self.Qk: Optional[int] = None
        self.dest: Optional[int] = None  # Tag do ROB
        self.instr: Optional[Instruction] = None
        self.exec_cycles: int = 0
        self.remaining: int = 0
        self.ready: bool = False
        self.result: Optional[Union[int, float]] = None
        self.rob_idx: Optional[int] = None

    def clear(self):
        self.busy = False
        self.op = None
        self.Vj = None
        self.Vk = None
        self.Qj = None
        self.Qk = None
        self.dest = None
        self.instr = None
        self.exec_cycles = 0
        self.remaining = 0
        self.ready = False
        self.result = None
        self.rob_idx = None

    def __repr__(self):
        if not self.busy:
            return f"{self.name}: Livre"
        return (f"{self.name}: {self.op} Vj={self.Vj} Vk={self.Vk} Qj={self.Qj} Qk={self.Qk} "
                f"dest={self.dest} instr={self.instr}")

class ROBEntry:
    """Entrada do buffer de reordenação (ROB)."""
    def __init__(self, idx: int, instr: Instruction, dest: Optional[str]):
        self.idx: int = idx
        self.instr: Instruction = instr
        self.dest: Optional[str] = dest  # registrador destino
        self.ready: bool = False
        self.state: str = 'ISSUE'  # ISSUE, EXEC, WB, COMMIT

        # Campos de valor específicos por tipo de instrução
        self.result: Optional[Union[int, float]] = None      # Para ADD, LD, etc.
        self.store_value: Optional[Union[int, float]] = None # Para SD
        self.branch_outcome: Optional[Tuple[bool, Optional[int]]] = None # Para BNE (taken, target_pc)

        # Para LD/SD: cálculo de endereço
        self.address: Optional[int] = None # Endereço de memória (para LD/SD)
        self.address_ready: bool = False # Flag que indica se o endereço foi calculado

        # Para desvios
        self.mispredicted: bool = False  # Para branch

    def __repr__(self):
        val_str = ""
        if self.result is not None:
            val_str = f"res={self.result}"
        elif self.store_value is not None:
            val_str = f"store_val={self.store_value}"
        elif self.branch_outcome is not None:
            val_str = f"branch={self.branch_outcome[0]},{self.branch_outcome[1]}"
        
        return (f"ROB{self.idx}: {self.instr} dest={self.dest} {val_str} "
                f"ready={self.ready} state={self.state}")

class ReorderBuffer:
    """Buffer de reordenação (ROB)."""
    def __init__(self, size):
        self.entries: list[ROBEntry] = []
        self.size = size
        self.next_id = 0

    def is_full(self):
        return len(self.entries) >= self.size

    def get_next_id(self):
        """Retorna um ID único para a próxima entrada do ROB."""
        id_ = self.next_id
        # O ID pode dar a volta, assumindo que nunca haverá mais de 2*size entradas em voo
        self.next_id = (self.next_id + 1) % (self.size * 2)
        return id_

    def add(self, entry: ROBEntry):
        if self.is_full():
            raise Exception('ROB cheio')
        self.entries.append(entry)
        return entry.idx

    def remove(self):
        if self.entries:
            self.entries.pop(0)

    def __getitem__(self, idx: int) -> Optional[ROBEntry]:
        """Busca uma entrada do ROB pelo seu ID estável."""
        if idx is None:
            return None
        for entry in self.entries:
            if entry.idx == idx:
                return entry
        return None # Retorna None se não encontrar (pode ter sido flush)

    def __len__(self):
        return len(self.entries)

    def dump(self):
        if not self.entries:
            return 'ROB vazio.'
        return '\n'.join(str(e) for e in self.entries)

    def clear(self):
        self.entries.clear()

class BranchPredictor:
    """Preditor de desvio de 2 bits com saturação."""
    def __init__(self, table_size=64):
        self.correct = 0
        self.total = 0
        self.table_size = table_size
        # Tabela de predição: cada entrada tem 2 bits (0-3)
        # 0,1 = não desvia; 2,3 = desvia
        # Estados: 00 (forte não), 01 (fraco não), 10 (fraco sim), 11 (forte sim)
        self.prediction_table = [1] * table_size  # Inicializa com "fraco não desvia"
        
    def _get_index(self, instr):
        """Calcula índice na tabela baseado no endereço da instrução."""
        # Usa hash simples do texto da instrução como proxy do endereço
        return hash(instr.raw_text) % self.table_size
    
    def predict(self, instr):
        """Prediz se o desvio será tomado baseado no histórico."""
        index = self._get_index(instr)
        state = self.prediction_table[index]
        # Estados 0,1 = não desvia; Estados 2,3 = desvia
        return state >= 2
    
    def update(self, taken, predicted):
        """Atualiza o preditor com o resultado real do desvio."""
        self.total += 1
        if taken == predicted:
            self.correct += 1
    
    def update_prediction_table(self, instr, taken):
        """Atualiza a tabela de predição com saturação."""
        index = self._get_index(instr)
        state = self.prediction_table[index]
        
        if taken:
            # Desvio foi tomado: move em direção a "desvia" (máximo 3)
            self.prediction_table[index] = min(3, state + 1)
        else:
            # Desvio não foi tomado: move em direção a "não desvia" (mínimo 0)
            self.prediction_table[index] = max(0, state - 1)

    def accuracy(self):
        if self.total == 0:
            return 1.0
        return self.correct / self.total

# Outras estruturas utilitárias podem ser adicionadas aqui 