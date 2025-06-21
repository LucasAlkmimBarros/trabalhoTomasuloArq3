# Simulador Didático do Algoritmo de Tomasulo

Este projeto é um simulador didático do algoritmo de Tomasulo com interface gráfica local (Tkinter), focado em instruções MIPS simplificadas, execução fora de ordem, estações de reserva, buffer de reordenação (ROB) e especulação de desvios.

## Funcionalidades
- Simulação passo a passo do algoritmo de Tomasulo
- Suporte a instruções MIPS (exemplo em `mips_example.txt`)
- Visualização de estações de reserva, tabela de registradores e ROB
- Suporte à execução fora de ordem e especulação de desvios
- Cálculo de métricas: IPC, ciclos totais, stalls, taxa de acerto de desvio (opcional)

## Requisitos
- Python 3.8+
- Tkinter (já incluso na maioria das instalações Python)

## Estrutura dos Arquivos
- `core.py`: Estruturas centrais (instrução, registradores, RS, ROB, preditor)
- `simulator.py`: Lógica do simulador, ciclos, métricas
- `gui.py`: Interface gráfica (Tkinter)
- `mips_example.txt`: Exemplo de instruções MIPS
- `README.md`: Este arquivo

## Como Executar
1. Certifique-se de ter o Python instalado (Tkinter incluso)
2. Clone ou baixe este repositório
3. Execute o simulador:

```bash
python gui.py
```

4. Cole ou carregue um arquivo de instruções MIPS (exemplo: `mips_example.txt`)
5. Use os botões para avançar ciclos, resetar ou visualizar métricas

## Exemplo de Instruções MIPS
Veja o arquivo `mips_example.txt` para um exemplo didático:

```
ADDI R1, R0, 0
ADDI R2, R0, 32
ADDI F2, F0, 2

LOOP: LD F0, 0(R1)
MUL F4, F0, F2
SD F4, 0(R1)
ADDI R1, R1, 8
BNE R1, R2, LOOP
```

## Observações
- Comentários em linhas iniciadas por `#` são ignorados
- O simulador é didático: não cobre todos os detalhes do hardware real, mas ilustra os conceitos principais do algoritmo de Tomasulo

## Licença
MIT 