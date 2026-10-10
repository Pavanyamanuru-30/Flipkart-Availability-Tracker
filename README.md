# Flipkart Regional Availability Tracker

This project provides automated tools to check the real-time delivery availability of products on Flipkart across thousands of regional PIN codes. 

It is especially useful for verifying stock glitches, such as when a product says "Only X left" but shows out of stock for your specific location.

## Features

* **Tracker Generator (`generate_tracker.py`):** Parses the official India Post PIN code directory to generate a structured Excel/CSV tracker file for specific regions (e.g., South Indian states).
* **PIN Scanner (`flipkart_pin_scanner.py`):** Uses asynchronous threading to rapidly test a Flipkart product URL against thousands of PIN codes to determine where it is genuinely available for delivery.
* **Open Source Integration:** The PIN Scanner logic is adapted from the open-source [flipkart-pin-checker](https://github.com/MacintoshTavish/flipkart-pin-checker) project.

## Prerequisites

* Python 3.10+
* Required libraries (install via `requirements.txt`)

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/Flipkart-Availability-Tracker.git
   cd Flipkart-Availability-Tracker
   ```
2. Install the required Python packages:
   ```bash
   python -m pip install -r requirements.txt
   ```
3. Download the official India Post PIN code dataset (CSV) from `data.gov.in` and place it in the project root as `india_post_pincodes.csv`.

## Usage

### 1. Generate the Tracker
Filter the massive PIN code dataset down to the region you care about (e.g., South India).
```bash
python generate_tracker.py
```
*Outputs: `south_india_delivery_tracker.xlsx` and `south_india_delivery_tracker.csv`*

### 2. Scan Availability
Run the scanner against a specific product URL to check its availability across the generated PIN codes.
```bash
python flipkart_pin_scanner.py "<FLIPKART_PRODUCT_URL>" --mode full --states "KARNATAKA,TAMIL NADU,KERALA,ANDHRA PRADESH,TELANGANA,PUDUCHERRY,LAKSHADWEEP,ANDAMAN & NICOBAR ISLANDS" --csv india_post_pincodes.csv --out CMF_Phone_Availability.csv
```

## Disclaimer
This project is for educational and personal use only. Automated scanning may violate Flipkart's Terms of Service if abused. Please use responsibly and do not overload the servers.
