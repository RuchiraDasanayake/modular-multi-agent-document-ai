import json
import matplotlib.pyplot as plt
import pandas as pd

def plot_simulation():
    try:
        with open('simulation_results.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("Error: simulation_results.json not found. Run jobs/simulation.py first.")
        return

    df = pd.DataFrame(data)
    
    # Create the plot
    plt.figure(figsize=(12, 6))
    
    # Plot F1 Scores
    plt.plot(df.index, df['f1'], marker='o', linestyle='-', color='b', alpha=0.5, label='F1 Score')
    
    # Highlight Phases
    plt.axvline(x=20, color='r', linestyle='--', label='Promotion Job (Learning)')
    
    # Add labels and title
    plt.title('AHMN System Learning Curve: F1 Score over Time')
    plt.xlabel('Iteration (Document Processed)')
    plt.ylabel('F1 Score')
    plt.legend()
    plt.grid(True)
    
    # Annotate
    plt.text(5, 0.5, 'Phase 1: Random/Manual\n(Low Performance)', fontsize=10, bbox=dict(facecolor='white', alpha=0.8))
    plt.text(22, 0.9, 'Phase 2: Learned Policy\n(High Performance)', fontsize=10, bbox=dict(facecolor='white', alpha=0.8))
    
    plt.savefig('learning_curve.png')
    print("Plot saved to 'learning_curve.png'")
    plt.show()

if __name__ == "__main__":
    plot_simulation()
