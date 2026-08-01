# tick-ingestion
Data ingestion and processing repository. For API requests, data cleaning, and normalizing.

# Tick Data Ingestion from NEON

The National Ecological Observation Network has been sampling ticks at sites across the country. The neon_tick_data downloads all data available through the NEON API. It is customizable so that you can limit only to certain months. The data is originally stored as one csv per site per month.  The final dataset appends all the possible sites and months.

tidy_ticks cleans the dataset and joins it with the taxonomy of the specific tick family that was found in the location. The dataset it produces gives us all obesrvations per site, per collection date, per taxonomy.

Visits that were sampled but caught nothing are kept as rows with individualCount=0. For larvaes (which are going to be a lot of disturb the count), they are flagged in the dataset incase we want to leave them out.
