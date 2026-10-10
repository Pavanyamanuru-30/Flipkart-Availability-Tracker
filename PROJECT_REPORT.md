# Project Report: Flipkart Regional Availability Tracker

## 1. Executive Summary
The **Flipkart Regional Availability Tracker** is a high-speed, asynchronous web application designed to systematically audit product availability across thousands of Indian PIN codes. 

E-commerce platforms frequently display global stock counters (e.g., "Only 3 left in stock"), which can mislead consumers if the product is restricted to specific regional warehouses. This project solves that discrepancy by automating the verification of delivery availability, exact pricing, and estimated delivery times across hyper-local regions.

## 2. Project Objectives
* **Transparency:** Uncover actual regional stock availability hidden behind generic out-of-stock messages.
* **Automation:** Eliminate the manual process of entering individual PIN codes on the e-commerce storefront.
* **Speed:** Execute thousands of queries in seconds using asynchronous I/O rather than traditional browser automation.
* **Analytics:** Provide persistent historical data to identify restock patterns and regional pricing differences.

## 3. Scope of the Application
The application is scoped strictly to **Flipkart's internal page-fetch API**. It leverages official India Post directory data to ensure only mathematically valid, real-world PIN codes are queried.

### In-Scope:
* High-concurrency scraping of Flipkart product availability.
* IP rotation for anti-ban resilience.
* Multi-product matrix scanning.
* Data extraction (Price, Availability, Delivery Date, Specific Neighborhood Name).
* Excel and CSV export functionality.

### Out-of-Scope:
* Automated purchasing or cart-checkout functionalities.
* Scraping platforms other than Flipkart (e.g., Amazon, Myntra).
* Cloud deployment (currently scoped as a local prototype for v1.0).

## 4. Key Features & Deliverables
1. **Interactive Web Interface:** A seamless UI built on Streamlit, fully themed, allowing users to input URLs and select granular target locations (State > District).
2. **High-Speed Async Engine:** Achieves a massive speedup over traditional scraping by using Python's `aiohttp` and `asyncio`, processing hundreds of PIN codes per minute.
3. **Smart IP Rotation:** Integrated proxy pool fetching to bypass HTTP 403/429 rate limits during massive state-wide scans.
4. **Data Enrichment:** Joins Flipkart's raw JSON responses with government postal data to map arbitrary 6-digit codes to human-readable post office/neighborhood names.
5. **Historical Analytics Database:** An integrated SQLite database that logs every query, powering an analytics dashboard for tracking long-term stock trends.

## 5. Results & Conclusion
Version 1.0 successfully transitions a proof-of-concept Python script into a robust, commercial-grade local web application. It handles edge cases (like rate limiting and network timeouts) gracefully and provides immediately actionable data through live-streaming tables and Excel exports. The foundation laid here is highly scalable and ready for future cloud deployment via Docker and Celery background workers.
