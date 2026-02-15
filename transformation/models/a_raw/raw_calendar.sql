MODEL (
  name a_raw.calendar,
  description 'BI calendar dimension table covering 1900-01-01 through 2049-12-31',
  kind FULL,
  grain full_date,
  columns (
    date_key INT,
    full_date DATE,
    year INT,
    quarter INT,
    month INT,
    month_name TEXT,
    day_of_month INT,
    day_of_week INT,
    day_name TEXT,
    week_of_year INT,
    is_weekend BOOLEAN,
    is_leap_year BOOLEAN,
    days_in_month INT,
    year_month TEXT,
    year_quarter TEXT,
    first_day_of_month DATE,
    last_day_of_month DATE,
    first_day_of_quarter DATE,
    last_day_of_quarter DATE,
    first_day_of_year DATE,
    last_day_of_year DATE
  ),
  column_descriptions (
    date_key = 'Integer surrogate key in YYYYMMDD format',
    full_date = 'The calendar date',
    year = 'Four-digit year (e.g. 2024)',
    quarter = 'Quarter of the year (1-4)',
    month = 'Month of the year (1-12)',
    month_name = 'Full month name (e.g. January)',
    day_of_month = 'Day of the month (1-31)',
    day_of_week = 'ISO day of the week (1 = Monday, 7 = Sunday)',
    day_name = 'Full day name (e.g. Monday)',
    week_of_year = 'ISO week number (1-53)',
    is_weekend = 'True if Saturday or Sunday',
    is_leap_year = 'True if the year is a leap year',
    days_in_month = 'Number of days in the month',
    year_month = 'Year and month in YYYY-MM format',
    year_quarter = 'Year and quarter in YYYY-QN format',
    first_day_of_month = 'First day of the month',
    last_day_of_month = 'Last day of the month',
    first_day_of_quarter = 'First day of the quarter',
    last_day_of_quarter = 'Last day of the quarter',
    first_day_of_year = 'January 1st of the year',
    last_day_of_year = 'December 31st of the year'
  )
);

WITH date_spine AS (
  SELECT
    UNNEST(GENERATE_SERIES(DATE '1900-01-01', DATE '2049-12-31', INTERVAL '1 day'))::DATE AS full_date
)
SELECT
  CAST(STRFTIME(full_date, '%Y%m%d') AS INT) AS date_key,
  full_date,
  EXTRACT(YEAR FROM full_date)::INT AS year,
  EXTRACT(QUARTER FROM full_date)::INT AS quarter,
  EXTRACT(MONTH FROM full_date)::INT AS month,
  STRFTIME(full_date, '%B') AS month_name,
  EXTRACT(DAY FROM full_date)::INT AS day_of_month,
  EXTRACT(ISODOW FROM full_date)::INT AS day_of_week,
  STRFTIME(full_date, '%A') AS day_name,
  EXTRACT(WEEK FROM full_date)::INT AS week_of_year,
  EXTRACT(ISODOW FROM full_date) IN (6, 7) AS is_weekend,
  (EXTRACT(YEAR FROM full_date)::INT % 4 = 0
    AND (EXTRACT(YEAR FROM full_date)::INT % 100 != 0
      OR EXTRACT(YEAR FROM full_date)::INT % 400 = 0)) AS is_leap_year,
  EXTRACT(DAY FROM LAST_DAY(full_date))::INT AS days_in_month,
  STRFTIME(full_date, '%Y-%m') AS year_month,
  STRFTIME(full_date, '%Y') || '-Q' || EXTRACT(QUARTER FROM full_date)::INT AS year_quarter,
  DATE_TRUNC('month', full_date)::DATE AS first_day_of_month,
  LAST_DAY(full_date) AS last_day_of_month,
  DATE_TRUNC('quarter', full_date)::DATE AS first_day_of_quarter,
  (DATE_TRUNC('quarter', full_date) + INTERVAL '3 months' - INTERVAL '1 day')::DATE AS last_day_of_quarter,
  DATE_TRUNC('year', full_date)::DATE AS first_day_of_year,
  (DATE_TRUNC('year', full_date) + INTERVAL '1 year' - INTERVAL '1 day')::DATE AS last_day_of_year
FROM date_spine
