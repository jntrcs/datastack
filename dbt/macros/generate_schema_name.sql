{#
  dbt's default names custom schemas "<target schema>_<custom>" everywhere, e.g.
  PROD_MARTS. This override keeps that prefix in dev (DBT_DEV_MARTS, your sandbox)
  but uses the clean name in prod (MARTS). It's the pattern dbt's docs recommend.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- elif target.name == 'prod' -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        {{ target.schema }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
