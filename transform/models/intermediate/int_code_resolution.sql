{#-
    The heart of the privacy design.

    KBO's TypeOfEnterprise, Status, Classification and TypeOfAddress are coded, and the
    code table is the only authority on what a code means. Hardcoding "1 = natural person"
    would mean that the day FOD Economie renumbers the category, the pipeline quietly starts
    publishing sole traders' addresses. So every concept the project depends on is resolved
    here, by description, out of stg_code -- and `assert_expected_codes_resolve` fails the
    build the moment a concept stops resolving to exactly one code.

    Matching is deliberately an exact match on the normalised description rather than a
    LIKE: "niet actief" contains "actief", and a substring match would resolve
    `status_active` to the stopped companies. TypeOfAddress is the sharpest illustration:
    the registered office is described as plain "Zetel", and "Vestigingseenheid",
    "Oudste actieve vestigingseenheid" and "Bijkantoor" sit in the same category -- an
    exact match is what keeps the four apart.

    The accepted spellings are the Dutch ones the real extract actually carries (stg_code
    prefers NL, and KBO publishes no English at all). The English spellings are kept
    alongside them because they cost nothing and a future extract may add them; resolution
    does not depend on them.
-#}

with codes as (

    select
        category,
        code,
        description,
        lower(strip_accents(trim(description))) as description_normalised
    from {{ ref('stg_code') }}

),

concepts as (

    -- concept, category, and the accepted NL and EN spellings of its description.
    select * from (
        values
            ('natural_person',            'TypeOfEnterprise', ['natuurlijk persoon', 'natural person']),
            ('legal_person',              'TypeOfEnterprise', ['rechtspersoon', 'legal person']),
            ('status_active',             'Status',           ['actief', 'active']),
            -- 'zetel' is what the real extract says; 'maatschappelijke zetel' was the
            -- older wording and stays accepted. Neither can match the three
            -- establishment-side descriptions, which is the point of the exact match.
            ('address_registered_office', 'TypeOfAddress',    ['zetel', 'maatschappelijke zetel', 'registered office']),
            ('classification_main',       'Classification',   ['hoofdactiviteit', 'main activity'])
    ) as t (concept, category, accepted_descriptions)

),

final as (

    select
        concepts.concept,
        concepts.category,
        codes.code,
        codes.description
    from concepts
    inner join codes
        on codes.category = concepts.category
        and list_contains(concepts.accepted_descriptions, codes.description_normalised)

)

select * from final
