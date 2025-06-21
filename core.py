# core.py
"""
Módulo central: estruturas de dados e lógica do algoritmo de Tomasulo.
Inclui: instrução, registradores, estações de reserva, ROB, preditor de desvio.
"""

import re

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
        elif self.opcode == 'BNE':
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
        self.name = name
        self.op_type = op_type  # 'ADD', 'MUL', 'LOAD', 'STORE', 'BRANCH'
        self.busy = False
        self.op = None
        self.Vj = None
        self.Vk = None
        self.Qj = None
        self.Qk = None
        self.dest = None  # Tag do ROB
        self.instr = None
        self.exec_cycles = 0
        self.remaining = 0
        self.ready = False
        self.result = None
        self.rob_idx = None

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
    def __init__(self, idx, instr, dest):
        self.idx = idx
        self.instr = instr
        self.dest = dest  # registrador destino ou endereço
        self.value = None
        self.ready = False
        self.state = 'ISSUE'  # ISSUE, EXEC, WB, COMMIT
        self.mispredicted = False  # Para branch

    def __repr__(self):
        return (f"ROB{self.idx}: {self.instr} dest={self.dest} val={self.value} "
                f"ready={self.ready} state={self.state}")

class ReorderBuffer:
    """Buffer de reordenação (ROB)."""
    def __init__(self, size):
        self.entries = []
        self.size = size
        self.head = 0
        self.tail = 0
        self.count = 0

    def is_full(self):
        return self.count >= self.size

    def add(self, entry):
        if self.is_full():
            raise Exception('ROB cheio')
        self.entries.append(entry)
        self.count += 1
        return entry.idx

    def remove(self):
        if self.entries:
            self.entries.pop(0)
            self.count -= 1

    def __getitem__(self, idx):
        return self.entries[idx]

    def __len__(self):
        return len(self.entries)

    def dump(self):
        if not self.entries:
            return 'ROB vazio.'
        return '\n'.join(str(e) for e in self.entries)

class BranchPredictor:
    """Preditor de desvio simples (sempre não desvia)."""
    def __init__(self):
        self.correct = 0
        self.total = 0

    def predict(self, instr):
        # Sempre não desvia (pode ser melhorado)
        return False

    def update(self, taken, predicted):
        self.total += 1
        if taken == predicted:
            self.correct += 1

    def accuracy(self):
        if self.total == 0:
            return 1.0
        return self.correct / self.total

# Outras estruturas utilitárias podem ser adicionadas aqui 