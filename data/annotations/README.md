# Annotations (created by the team from real documents)

`capability_gold.csv` - real tender / award lines labelled with a capability key from
`backend/app/restructuring/taxonomy.py`. Columns: `text,capability`. Sources to label: World Bank
India contract descriptions and the BOQ of the demo tender. When this file has rows, `build_market.py`
reports the classifier's accuracy on them (the honest transfer estimate) and adds them to training.
