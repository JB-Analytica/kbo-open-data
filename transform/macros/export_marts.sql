{#-
    Write every mart to Parquet so the repo can publish a release without a warehouse.

    A run-operation rather than a post-hook: publishing is a deliberate act, not a side
    effect of building. It runs against the local warehouse the project always builds in;
    the cloud copy of the marts is made separately by `kbo publish`.

        dbt run-operation export_marts --project-dir transform --profiles-dir transform
        dbt run-operation export_marts --args '{output_dir: /tmp/out}' ...
-#}
{% macro export_marts(output_dir=none) %}

    {#- `project_root` is empty in a run-operation, so derive the default from the
        --project-dir that was actually passed. That makes the default correct both from
        the repo root (`--project-dir transform`) and from inside transform/ itself. -#}
    {%- set project_dir = invocation_args_dict.get('project_dir') or '.' -%}
    {%- set target_dir = output_dir or project_dir ~ '/../data/published' -%}

    {%- if execute -%}
        {%- set marts = [] -%}
        {%- for node in graph.nodes.values() -%}
            {%- if node.resource_type == 'model' and 'marts' in node.fqn -%}
                {%- do marts.append(node) -%}
            {%- endif -%}
        {%- endfor -%}

        {%- if marts | length == 0 -%}
            {%- do exceptions.raise_compiler_error(
                "export_marts found no models under models/marts. Run `dbt build` first."
            ) -%}
        {%- endif -%}

        {%- for node in marts | sort(attribute='name') -%}
            {%- set relation = api.Relation.create(
                database=node.database, schema=node.schema, identifier=node.alias
            ) -%}
            {%- set destination = target_dir ~ '/' ~ node.name ~ '.parquet' -%}
            {%- set sql -%}
                copy (select * from {{ relation }})
                to '{{ destination }}' (format parquet, compression zstd)
            {%- endset -%}
            {%- do run_query(sql) -%}
            {%- do log("exported " ~ node.name ~ " -> " ~ destination, info=true) -%}
        {%- endfor -%}
    {%- endif -%}

{% endmacro %}
