SELECT
  test_cases.chapter1,
  test_cases.chapter2,
  count(*)
FROM
  jscert.test_cases
GROUP BY
  test_cases.chapter1, test_cases.chapter2
ORDER BY
  test_cases.chapter1, test_cases.chapter2
;