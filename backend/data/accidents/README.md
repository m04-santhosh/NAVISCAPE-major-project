# Karnataka Accident Dataset — Data Directory

## Required File

Place the Karnataka Accident Dataset CSV here:

```
backend/data/accidents/karnataka_accidents.csv
```

## Download Instructions

1. Visit: https://www.kaggle.com/datasets/shubham2703/karnataka-accident-dataset
2. Sign in with a free Kaggle account
3. Click **Download** to get the ZIP
4. Extract the CSV file from the ZIP
5. Rename it to `karnataka_accidents.csv` if needed
6. Place it in this directory (`backend/data/accidents/`)

## Import

After placing the CSV, run from the `backend/` directory:

```bash
python import_accidents.py
```

## Dataset Notes

- **Coverage**: Primarily Bagalkot district, Karnataka, India
- **Source**: https://www.kaggle.com/datasets/shubham2703/karnataka-accident-dataset
- **Data type**: Historical accident records — NOT a live feed
- This is not complete Karnataka-wide accident data

## Expected CSV Columns

| CSV Column | DB Field | Required |
|---|---|---|
| Latitude | latitude | ✅ Yes |
| Longitude | longitude | ✅ Yes |
| DISTRICTNAME | district | No |
| Crime_No | crime_no | No (dedup key) |
| Year | year | No |
| Severity | severity | No |
| Main_Cause | main_cause | No |
| ... | ... | No |
