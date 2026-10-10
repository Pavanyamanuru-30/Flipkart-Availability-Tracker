import pandas as pd
import os

# Define South Indian states
SOUTH_INDIAN_STATES = [
    'KARNATAKA', 'TAMIL NADU', 'KERALA', 'ANDHRA PRADESH', 'TELANGANA', 'PUDUCHERRY', 'LAKSHADWEEP', 'ANDAMAN & NICOBAR ISLANDS'
]

def generate_tracker():
    dataset_path = 'india_post_pincodes.csv'
    
    if not os.path.exists(dataset_path):
        print(f"Error: {dataset_path} not found in the current directory.")
        return

    # Load dataset
    df = pd.read_csv(dataset_path, dtype=str)
    
    # Check if necessary columns exist (case-insensitive for safety, standardizing to lowercase for checking)
    cols = [col.lower() for col in df.columns]
    
    # We need 'pincode', 'statename', 'districtname'
    # Assuming columns might be 'pincode', 'stateName', 'Districtname'
    state_col = next((col for col in df.columns if 'state' in col.lower()), None)
    pin_col = next((col for col in df.columns if 'pin' in col.lower()), None)
    dist_col = next((col for col in df.columns if 'district' in col.lower()), None)

    if not all([state_col, pin_col, dist_col]):
        print("Could not find the necessary columns in the dataset.")
        print(f"Available columns: {df.columns.tolist()}")
        return

    # Filter for South Indian states
    south_df = df[df[state_col].str.upper().isin(SOUTH_INDIAN_STATES)].copy()
    
    # Keep only unique PIN codes and their details
    south_df = south_df.drop_duplicates(subset=[pin_col])
    
    # Select specific columns
    result_df = south_df[[pin_col, state_col, dist_col]].copy()
    
    # Add 'delivery-status' column
    result_df['delivery-status'] = 'NOT_CHECKED'
    
    # Rename columns for clarity
    result_df = result_df.rename(columns={
        pin_col: 'PIN Code',
        state_col: 'State',
        dist_col: 'District'
    })
    
    # Save the output files
    excel_path = 'south_india_delivery_tracker.xlsx'
    csv_path = 'south_india_delivery_tracker.csv'
    
    result_df.to_excel(excel_path, index=False)
    result_df.to_csv(csv_path, index=False)
    
    print(f"Processed {len(result_df)} South Indian PIN codes.")
    print(f"Files generated:\n- {os.path.abspath(excel_path)}\n- {os.path.abspath(csv_path)}")

if __name__ == '__main__':
    generate_tracker()
