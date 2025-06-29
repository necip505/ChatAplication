import pandas as pd
import matplotlib.pyplot as plt
import os
import glob

def plot_latency_data(csv_filepath):
    """
    Reads a latency CSV file and generates:
    1. A line plot of latency over time.
    2. A histogram of latency values.
    Plots are saved as PNG files.
    """
    try:
        df = pd.read_csv(csv_filepath)
    except FileNotFoundError:
        print(f"Error: File not found at {csv_filepath}")
        return
    except pd.errors.EmptyDataError:
        print(f"Error: File is empty at {csv_filepath}")
        return
    except Exception as e:
        print(f"Error reading {csv_filepath}: {e}")
        return

    if 'latency_ms' not in df.columns:
        print(f"Error: 'latency_ms' column not found in {csv_filepath}")
        return
    if 'log_timestamp' not in df.columns:
        print(f"Error: 'log_timestamp' column not found in {csv_filepath}")
        # As a fallback, we can use the index if timestamp is missing
        df['log_timestamp'] = pd.to_datetime(df.index, unit='s') # Or some other placeholder
        print("Warning: Using message index for time axis as 'log_timestamp' was missing.")
    else:
        # Convert log_timestamp to datetime objects, coercing errors
        df['log_timestamp'] = pd.to_datetime(df['log_timestamp'], errors='coerce')
        df.dropna(subset=['log_timestamp'], inplace=True) # Remove rows where conversion failed

    # Convert latency_ms to numeric, coercing errors
    df['latency_ms'] = pd.to_numeric(df['latency_ms'], errors='coerce')
    df.dropna(subset=['latency_ms'], inplace=True) # Remove rows where conversion failed

    if df.empty:
        print(f"No valid data to plot in {csv_filepath} after cleaning.")
        return

    base_filename = os.path.splitext(os.path.basename(csv_filepath))[0]

    # 1. Latency over Time plot
    plt.figure(figsize=(12, 6))
    plt.plot(df['log_timestamp'], df['latency_ms'], marker='o', linestyle='-', markersize=4)
    plt.title(f'Latency Over Time - {base_filename}')
    plt.xlabel('Time')
    plt.ylabel('Latency (ms)')
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    time_plot_filename = f'{base_filename}_time_plot.png'
    plt.savefig(time_plot_filename)
    plt.close()
    print(f"Saved time plot: {time_plot_filename}")

    # 2. Latency Histogram
    plt.figure(figsize=(10, 6))
    plt.hist(df['latency_ms'], bins=30, edgecolor='black')
    plt.title(f'Latency Distribution - {base_filename}')
    plt.xlabel('Latency (ms)')
    plt.ylabel('Frequency')
    plt.grid(axis='y')
    plt.tight_layout()
    hist_plot_filename = f'{base_filename}_histogram.png'
    plt.savefig(hist_plot_filename)
    plt.close()
    print(f"Saved histogram: {hist_plot_filename}")

if __name__ == "__main__":
    # Find all latency CSV files in the current directory
    csv_files = glob.glob("latency_*.csv")
    
    if not csv_files:
        print("No 'latency_*.csv' files found in the current directory.")
    else:
        print(f"Found latency files: {csv_files}")
        for f in csv_files:
            print(f"\nProcessing {f}...")
            try:
                plot_latency_data(f)
            except Exception as e:
                print(f"!!! An unexpected error occurred while processing {f}: {e}")
                print(f"!!! Skipping this file due to the error and attempting to continue with others.")
    print("\nDone processing all files.")