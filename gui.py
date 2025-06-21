# gui.py
"""
Interface gráfica (Tkinter) para o simulador de Tomasulo.
"""
import tkinter as tk
from tkinter import filedialog, font, ttk
from simulator import TomasuloSimulator

class TomasuloGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Simulador Tomasulo Didático")
        self.root.geometry("1400x900")
        self.root.minsize(1100, 700)
        self.root.configure(bg="#f4f6fa")
        self.sim = TomasuloSimulator()
        self.mono_font = font.Font(family="Consolas", size=12)
        self.title_font = font.Font(family="Arial", size=16, weight="bold")
        self.label_font = font.Font(family="Arial", size=13, weight="bold")
        self.create_widgets()
        self.update_views()

    def create_widgets(self):
        # Top: Instruções e botões
        frame_top = tk.Frame(self.root, bg="#f4f6fa")
        frame_top.pack(fill="x", padx=12, pady=(10, 0))
        self.text_instructions = tk.Text(frame_top, width=140, height=5, font=self.mono_font, bg="#fafdff", borderwidth=2, relief="groove")
        self.text_instructions.grid(row=0, column=0, columnspan=6, sticky="ew", padx=2, pady=2)
        self.btn_load = tk.Button(frame_top, text="Carregar arquivo", command=self.load_file, font=self.label_font, bg="#e0e7ef", relief="ridge")
        self.btn_load.grid(row=1, column=0, padx=5, pady=8, sticky="w")
        self.btn_reset = tk.Button(frame_top, text="Resetar", command=self.reset, font=self.label_font, bg="#e0e7ef", relief="ridge")
        self.btn_reset.grid(row=1, column=1, padx=5, pady=8, sticky="w")
        self.btn_step = tk.Button(frame_top, text="Próximo ciclo", command=self.step, font=self.label_font, bg="#e0e7ef", relief="ridge")
        self.btn_step.grid(row=1, column=2, padx=5, pady=8, sticky="w")
        self.cycle_label = tk.Label(frame_top, text="Ciclo: 0", font=self.label_font, bg="#f4f6fa", fg="#2a3a5e")
        self.cycle_label.grid(row=1, column=3, padx=20, pady=8, sticky="e")

        # Separador
        sep1 = tk.Frame(self.root, height=2, bg="#b0b8c9")
        sep1.pack(fill="x", padx=0, pady=8)

        # Main: RS, ROB, Registradores
        frame_main = tk.Frame(self.root, bg="#f4f6fa")
        frame_main.pack(fill="both", expand=True, padx=12, pady=0)
        frame_main.columnconfigure(0, weight=1)
        frame_main.columnconfigure(1, weight=1)
        frame_main.columnconfigure(2, weight=1)
        frame_main.rowconfigure(0, weight=1)

        # LabelFrames para cada seção
        lf_rs = tk.LabelFrame(frame_main, text="Estações de Reserva", font=self.title_font, bg="#f4f6fa", fg="#2a3a5e", labelanchor='n')
        lf_rs.grid(row=0, column=0, sticky="nsew", padx=8, pady=4)
        lf_rob = tk.LabelFrame(frame_main, text="ROB (Buffer de Reordenação)", font=self.title_font, bg="#f4f6fa", fg="#2a3a5e", labelanchor='n')
        lf_rob.grid(row=0, column=1, sticky="nsew", padx=8, pady=4)
        lf_regs = tk.LabelFrame(frame_main, text="Registradores", font=self.title_font, bg="#f4f6fa", fg="#2a3a5e", labelanchor='n')
        lf_regs.grid(row=0, column=2, sticky="nsew", padx=8, pady=4)

        # Treeview para RS
        self.tree_rs = ttk.Treeview(lf_rs, columns=("Nome", "Op", "Vj", "Vk", "Qj", "Qk", "Dest", "Instr"), show="headings", height=16)
        for col, w in zip(["Nome", "Op", "Vj", "Vk", "Qj", "Qk", "Dest", "Instr"], [80, 50, 90, 90, 50, 50, 60, 320]):
            self.tree_rs.heading(col, text=col)
            self.tree_rs.column(col, width=w, anchor="center")
        self.tree_rs.pack(fill="both", expand=True, padx=2, pady=2)
        self.rs_legend = tk.Label(lf_rs, text="Legenda: Nome = Estação | Op = Operação | Vj/Vk = Valores | Qj/Qk = Dependências | Dest = ROB | Instr = Instrução", font=("Arial", 10), bg="#f4f6fa", fg="#555")
        self.rs_legend.pack(anchor="w", padx=2, pady=(0,2))

        # Treeview para ROB
        self.tree_rob = ttk.Treeview(lf_rob, columns=("ID", "Instr", "Dest", "Valor", "Pronto", "Estado"), show="headings", height=16)
        for col, w in zip(["ID", "Instr", "Dest", "Valor", "Pronto", "Estado"], [40, 260, 60, 90, 70, 80]):
            self.tree_rob.heading(col, text=col)
            self.tree_rob.column(col, width=w, anchor="center")
        self.tree_rob.pack(fill="both", expand=True, padx=2, pady=2)
        self.rob_legend = tk.Label(lf_rob, text="Legenda: ID = Entrada | Instr = Instrução | Dest = Destino | Valor = Resultado | Pronto = WB | Estado = Estágio", font=("Arial", 10), bg="#f4f6fa", fg="#555")
        self.rob_legend.pack(anchor="w", padx=2, pady=(0,2))

        # Treeview para Registradores
        self.tree_regs = ttk.Treeview(lf_regs, columns=("Reg", "Valor"), show="headings", height=16)
        self.tree_regs.heading("Reg", text="Registrador")
        self.tree_regs.heading("Valor", text="Valor")
        self.tree_regs.column("Reg", width=90, anchor="center")
        self.tree_regs.column("Valor", width=120, anchor="center")
        self.tree_regs.pack(fill="both", expand=True, padx=2, pady=2)
        self.reg_legend = tk.Label(lf_regs, text="Legenda: Inteiros = R0..R31 | FP = F0..F31", font=("Arial", 10), bg="#f4f6fa", fg="#555")
        self.reg_legend.pack(anchor="w", padx=2, pady=(0,2))

        # Separador
        sep2 = tk.Frame(self.root, height=2, bg="#b0b8c9")
        sep2.pack(fill="x", padx=0, pady=8)

        # Métricas (barra inferior)
        frame_metrics = tk.Frame(self.root, bg="#eaf2e3")
        frame_metrics.pack(fill="x", padx=0, pady=(0, 0), side="bottom")
        self.label_metrics = tk.Label(frame_metrics, text="Métricas de Desempenho", font=self.title_font, bg="#eaf2e3", fg="#2a3a5e")
        self.label_metrics.pack(anchor="w", padx=12, pady=(2, 0))
        self.text_metrics = tk.Label(frame_metrics, font=("Consolas", 15, "bold"), bg="#eaf2e3", anchor="w")
        self.text_metrics.pack(fill="x", padx=12, pady=(0, 8))

    def load_file(self):
        filename = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if filename:
            with open(filename, 'r') as f:
                content = f.read()
                self.text_instructions.delete('1.0', tk.END)
                self.text_instructions.insert(tk.END, content)
            self.sim.load_instructions(content.splitlines())
            self.update_views()

    def reset(self):
        # Recarrega as instruções visíveis na caixa de texto
        content = self.text_instructions.get('1.0', tk.END)
        self.sim.load_instructions(content.splitlines())
        self.update_views()

    def step(self):
        self.sim.step()
        self.update_views()

    def update_views(self):
        # Atualiza ciclo
        self.cycle_label.config(text=f"Ciclo: {self.sim.cycle}")

        # Atualiza RS
        for i in self.tree_rs.get_children():
            self.tree_rs.delete(i)
        # Descobrir quais RS estão em execução (ocupando UF)
        executing_rs = set()
        for uflist in self.sim.functional_units.values():
            for uf in uflist:
                if uf['rs'] is not None:
                    executing_rs.add(uf['rs'])
        for rs in self.sim.reservation_stations:
            color = "#e0e7ef" if rs.busy else "#fafdff"
            stage = rs.instr.opcode if rs.busy and rs.instr else "-"
            values = [rs.name, rs.op or '-', str(rs.Vj)[:9], str(rs.Vk)[:9], str(rs.Qj)[:4], str(rs.Qk)[:4], str(rs.dest)[:4], str(rs.instr)[:40] if rs.instr else '-']
            tags = (stage,)
            if rs in executing_rs:
                tags = ("EXECUTING",)
            self.tree_rs.insert('', 'end', values=values, tags=tags)
        self.tree_rs.tag_configure('LD', background="#d0f0ff")
        self.tree_rs.tag_configure('SD', background="#ffe0e0")
        self.tree_rs.tag_configure('ADD', background="#e0ffe0")
        self.tree_rs.tag_configure('SUB', background="#e0ffe0")
        self.tree_rs.tag_configure('MUL', background="#fff0d0")
        self.tree_rs.tag_configure('-', background="#fafdff")
        self.tree_rs.tag_configure('EXECUTING', background="#fff9b1")  # Amarelo claro para execução

        # Atualiza ROB
        for i in self.tree_rob.get_children():
            self.tree_rob.delete(i)
        for entry in self.sim.rob.entries:
            color = "#fafdff"
            if entry.state == 'EXEC':
                color = "#d0f0ff"
            elif entry.state == 'WB':
                color = "#e0ffe0"
            elif entry.state == 'COMMIT':
                color = "#fff0d0"
            values = [entry.idx, str(entry.instr)[:28], str(entry.dest)[:5], str(entry.value)[:9], str(entry.ready), entry.state]
            self.tree_rob.insert('', 'end', values=values, tags=(entry.state,))
        self.tree_rob.tag_configure('EXEC', background="#d0f0ff")
        self.tree_rob.tag_configure('WB', background="#e0ffe0")
        self.tree_rob.tag_configure('COMMIT', background="#fff0d0")
        self.tree_rob.tag_configure('ISSUE', background="#fafdff")

        # Atualiza Registradores
        for i in self.tree_regs.get_children():
            self.tree_regs.delete(i)
        regs = self.sim.register_file.int_regs
        fpregs = self.sim.register_file.fp_regs
        for k, v in regs.items():
            if v != 0:
                self.tree_regs.insert('', 'end', values=(k, v), tags=('int',))
        for k, v in fpregs.items():
            if v != 0:
                self.tree_regs.insert('', 'end', values=(k, f"{v:.2f}"), tags=('fp',))
        self.tree_regs.tag_configure('int', background="#fafdff")
        self.tree_regs.tag_configure('fp', background="#fafdff")

        # Atualizar métricas automaticamente
        metrics = self.sim.get_metrics()
        metrics_str = f"Ciclos: {metrics['Ciclos']}   |   IPC: {metrics['IPC']}   |   Stalls: {metrics['Stalls']}   |   Taxa de acerto de desvio: {metrics['Taxa de acerto de desvio']}"
        self.text_metrics.config(text=metrics_str, fg="#2a3a5e")

if __name__ == "__main__":
    root = tk.Tk()
    app = TomasuloGUI(root)
    root.mainloop() 