{{ config(
  materialized='table',
  description='Calendar table covering 1900-01-01 through 2049-12-31'
) }}

WITH dates AS (
  SELECT
    t.date::DATE AS date
  FROM RANGE('1900-01-01'::DATE, '2045-01-01'::DATE, INTERVAL '1' DAY) AS t(date)
)
SELECT
  YEAR(date) * 10000 + MONTH(date) * 100 + DAY(date) AS date_key, /* Integer surrogate key in YYYYMMDD format */
  date, /* The calendar date */
  YEAR(date) AS year, /* Four-digit year (e.g. 2024) */
  QUARTER(date) AS quarter, /* Quarter of the year (1-4) */
  MONTH(date) AS month, /* Month of the year (1-12) */
  MONTHNAME(date) AS month_name, /* Full month name (e.g. January) */
  DAY(date) AS day_of_month, /* Day of the month (1-31) */
  ISODOW(date) AS day_of_week, /* ISO day of the week (1 = Monday, 7 = Sunday) */
  DAYNAME(date) AS day_name, /* Full day name (e.g. Monday) */
  WEEK(date) AS week_of_year, /* ISO week number (1-53) */
  ISODOW(date) IN (6, 7) AS is_weekend, /* True if Saturday or Sunday */
  DAYOFYEAR(MAKE_DATE(YEAR(date), 12, 31)) = 366 AS is_leap_year, /* True if the year is a leap year */
  DAY(LAST_DAY(date)) AS days_in_month, /* Number of days in the month */
  STRFTIME(date, '%Y-%m') AS year_month, /* Year and month in YYYY-MM format */
  STRFTIME(date, '%Y') || '-Q' || QUARTER(date) AS year_quarter, /* Year and quarter in YYYY-QN format */
  DATE_TRUNC('MONTH', date)::DATE AS first_day_of_month, /* First day of the month */
  LAST_DAY(date) AS last_day_of_month, /* Last day of the month */
  DATE_TRUNC('QUARTER', date)::DATE AS first_day_of_quarter, /* First day of the quarter */
  (
    DATE_TRUNC('QUARTER', date) + INTERVAL 3 MONTH - INTERVAL 1 DAY
  )::DATE AS last_day_of_quarter, /* Last day of the quarter */
  MAKE_DATE(YEAR(date), 1, 1) AS first_day_of_year, /* January 1st of the year */
  MAKE_DATE(YEAR(date), 12, 31) AS last_day_of_year /* December 31st of the year */
FROM dates