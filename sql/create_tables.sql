drop table if exists glottolog_languages;

create table glottolog_languages (
	glottocode VARCHAR(20) PRIMARY KEY,
    name TEXT,
    level TEXT,
    countries TEXT,
    macroareas TEXT,
    latitude TEXT,
    longitude TEXT,
    iso639_3 VARCHAR(10),
    status TEXT
);

