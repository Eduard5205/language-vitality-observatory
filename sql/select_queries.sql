select count(*) from glottolog_languages

-- there are 7837 languages documented in glottolog

select status, count (*) from glottolog_languages
group by status

-- only 2694 of them are not endangered

select macroareas, count(*) from glottolog_languages
group by macroareas 

-- countinents with highest documented linguistic diversity are Africa and Papunesia
-- Australia and the Americas are less diverse linguistically
-- Eurasia is quite diverse, but notably less than Africa and Papunesia

SELECT
    macroareas,
    COUNT(*) AS total_languages,
    COUNT(*) FILTER (WHERE status != 'not endangered') AS endangered_languages,
    ROUND(
        COUNT(*) FILTER (WHERE status != 'not endangered')::NUMERIC
        / COUNT(*),
        3
    ) AS endangerment_coefficient
FROM glottolog_languages
GROUP BY macroareas
ORDER BY endangerment_coefficient DESC;

-- Australia has the highest endargerment coefficient. Almost 99% of the languages are endangered there
-- South America also exhibits weak linguistic preservation: around 92% of its languages are endangered
-- Africa is the only continent where less than half of all languages are endangered (41%). 

CREATE VIEW glottolog_language_countries AS
SELECT
    glottocode,
    name,
    level,
    TRIM(country) AS country,
    macroareas,
    latitude,
    longitude,
    iso639_3,
    status
FROM glottolog_languages,
LATERAL unnest(string_to_array(countries, ',')) AS country;

create view glottolog_preservation_monitor as 
select country, 
count (*) filter (where status='not endangered') as not_endangered,
count (*) filter (where status='threatened') as threatened,
count (*) filter (where status='moribund') as moribund,
count (*) filter (where status='shifting') as shifting,
count (*) filter (where status='nearly extinct') as nearly_extinct,
count (*) filter (where status='extinct') as extinct,
count (*) as languages_in_total,
ROUND(COUNT(*) FILTER (WHERE status = 'not endangered')::NUMERIC/COUNT(*),
        3) AS preservation_coefficient from glottolog_language_countries
group by country;

select * from glottolog_preservation_monitor
order by languages_in_total desc;
--Papua-New Guinea is the most linguistically rich country in the wolrd, contains around 850 languages within its oborders
--43% of Papuan languages are yet not endangered

select * from glottolog_preservation_monitor
order by preservation_coefficient desc, languages_in_total desc;
--Rwanda shows an impressive result: none of its 8 laguages are endangered, same goes for Burundi
-- High preservation coefficient does not automatically mean successful language policy.
-- It may reflect lower urbanization, weaker school integration, geographic isolation,
-- strong local community transmission, or state support.
-- To isolate policy effects, we need additional country-level variables.

SELECT
    country,
    extinct,
    languages_in_total,
    ROUND(extinct::NUMERIC / languages_in_total, 3) AS extinction_coefficient
FROM glottolog_preservation_monitor
ORDER BY extinction_coefficient desc;
-- Australia has the highest extinction coefficient in the dataset.
-- More than half of the documented languages are classified as extinct there.
--
-- The United States also exhibits a high extinction coefficient.
--
-- One possible explanation is the historical impact of settler colonialism,
-- including displacement, assimilation policies, and demographic collapse among
-- Indigenous populations.