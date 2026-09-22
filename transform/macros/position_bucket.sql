{% macro position_bucket(expr) -%}
case
    when {{ expr }} is null then 'FIELD'
    when lower(trim({{ expr }})) in ('gk', 'goalkeeper', 'goalie')
         or lower({{ expr }}) ~ 'goal.?keep'
        then 'GK'
    when lower(trim({{ expr }})) in (
            'df', 'defender', 'cb', 'lb', 'rb', 'lwb', 'rwb', 'wb',
            'centre-back', 'center-back', 'centre back', 'center back',
            'left-back', 'right-back', 'left back', 'right back',
            'full-back', 'full back', 'central defender'
        )
         or lower({{ expr }}) ~ 'back|defen[cs]'
        then 'DEF'
    when lower(trim({{ expr }})) in (
            'mf', 'midfielder', 'cm', 'cdm', 'cam', 'dm', 'am', 'lm', 'rm',
            'attacking midfielder', 'defensive midfielder', 'central midfielder'
        )
         or lower({{ expr }}) ~ 'midfield'
        then 'MID'
    when lower(trim({{ expr }})) in (
            'fw', 'forward', 'striker', 'winger', 'st', 'cf', 'lw', 'rw', 'ss',
            'left winger', 'right winger', 'inside forward'
        )
         or lower({{ expr }}) ~ 'forward|striker|wing'
        then 'ATT'
    else 'FIELD'
end
{%- endmacro %}
