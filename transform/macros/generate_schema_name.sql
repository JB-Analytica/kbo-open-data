{#-
    Use the configured schema verbatim (`staging`, `intermediate`, `marts`) instead of
    dbt's default `<target_schema>_<custom_schema>`. The published database has three
    named layers and one anonymous default, and `main_marts` would leak the target's
    name into the thing we publish.
-#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
