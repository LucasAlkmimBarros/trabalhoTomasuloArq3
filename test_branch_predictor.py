# test_branch_predictor.py
"""
Teste simples para demonstrar a melhoria do preditor de desvio
"""
from core import BranchPredictor, Instruction

def test_branch_predictor():
    print("=== Teste do Preditor de Desvio Melhorado ===\n")
    
    predictor = BranchPredictor()
    
    # Cria uma instrução de desvio de exemplo
    branch_instr = Instruction("LOOP: BNE $t0, $t1, END")
    
    print("Cenário 1: Desvio que inicialmente não é tomado, depois sempre é tomado")
    print("-" * 60)
    
    # Simula uma sequência de desvios onde o padrão muda
    scenarios = [
        (False, "Primeira execução - não desvia"),
        (False, "Segunda execução - não desvia"), 
        (True, "Terceira execução - desvia (padrão muda)"),
        (True, "Quarta execução - desvia"),
        (True, "Quinta execução - desvia"),
        (True, "Sexta execução - desvia"),
    ]
    
    for i, (actual_taken, description) in enumerate(scenarios, 1):
        # Faz a predição
        predicted = predictor.predict(branch_instr)
        
        # Atualiza o preditor com o resultado real
        predictor.update(actual_taken, predicted)
        predictor.update_prediction_table(branch_instr, actual_taken)
        
        # Mostra resultado
        correct = "✓" if actual_taken == predicted else "✗"
        print(f"Execução {i}: {description}")
        print(f"  Predito: {'Desvia' if predicted else 'Não desvia'}")
        print(f"  Real: {'Desvia' if actual_taken else 'Não desvia'}")
        print(f"  Resultado: {correct} {'Correto' if actual_taken == predicted else 'Incorreto'}")
        print(f"  Taxa de acerto atual: {predictor.accuracy():.1%}")
        print()
    
    print("Cenário 2: Teste com diferentes instruções")
    print("-" * 60)
    
    # Testa com diferentes instruções para mostrar que cada uma tem seu histórico
    instr1 = Instruction("BEQ $t0, $zero, SKIP")
    instr2 = Instruction("BNEZ $t1, LOOP")
    
    # Instrução 1: sempre desvia
    for i in range(3):
        pred = predictor.predict(instr1)
        predictor.update(True, pred)
        predictor.update_prediction_table(instr1, True)
        print(f"Instr1 execução {i+1}: Predito={pred}, Real=True, Acerto={'✓' if pred else '✗'}")
    
    print()
    
    # Instrução 2: nunca desvia  
    for i in range(3):
        pred = predictor.predict(instr2)
        predictor.update(False, pred)
        predictor.update_prediction_table(instr2, False)
        print(f"Instr2 execução {i+1}: Predito={pred}, Real=False, Acerto={'✓' if not pred else '✗'}")
    
    print(f"\nTaxa de acerto final: {predictor.accuracy():.1%}")
    print(f"Total de predições: {predictor.total}")
    print(f"Predições corretas: {predictor.correct}")

if __name__ == "__main__":
    test_branch_predictor()
