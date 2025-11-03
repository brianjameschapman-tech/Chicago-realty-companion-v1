# Realty Companion Pro – Chicago Edition
# © 2025 Brian James Chapman. All Rights Reserved.
# Licensed under the MIT License – see LICENSE file for details.
import html, json
import pandas as pd, streamlit as st
from jsonschema import validate, ValidationError
from pathlib import Path
from engine import load_json, run_all

st.set_page_config(page_title='Realty Companion Pro – Chicago Edition', page_icon='📈', layout='centered')
st.title('Realty Companion Pro – Chicago Edition')
st.caption('Novice-first flip evaluator with auto-tuned Monte Carlo (Engineer vs Consumer lenses).')

regional_map = load_json('data/regional_headwinds.json', {})
schema = {
  "type":"object",
  "properties":{
    "address":{"type":"string"},
    "region_ring":{"enum":["Urban Core","Inner Collar","Outer Collar"]},
    "purchase":{"type":"number","minimum":10000},
    "rehab":{"type":"number","minimum":0},
    "carry":{"type":"number","minimum":0},
    "selling_pct":{"type":"number","minimum":0,"maximum":0.12},
    "projected_sale":{"type":"number","minimum":10000},
    "hold_months":{"type":"number","minimum":1},
    "permit_delay_days":{"type":"integer","minimum":0,"maximum":180},
    "tax_drag":{"type":"number","minimum":0,"maximum":0.05},
    "ltv":{"type":"number","minimum":0,"maximum":1},
    "loan_rate_annual":{"type":"number","minimum":0,"maximum":0.25}
  },
  "required":["address","region_ring","purchase","rehab","carry","selling_pct","projected_sale","hold_months","permit_delay_days","tax_drag","ltv","loan_rate_annual"]
}

with st.expander('Quick guide', expanded=True):
    st.markdown('- Enter deal → Run simulations → Read GO/CAUTION.\n- Bars auto-tune each run. CSV exports included.')

st.header('1) Deal')
with st.form('deal'):
    address = st.text_input('Address', value='1234 W Belmont Ave')
    region = st.selectbox('Region (Chicagoland ring)', ['Urban Core','Inner Collar','Outer Collar'], index=0)
    c1,c2 = st.columns(2)
    with c1:
        purchase = st.number_input('Purchase price', min_value=10000, value=310000, step=5000)
        rehab    = st.number_input('Rehab estimate', min_value=0, value=50000, step=1000)
        selling_pct = st.number_input('Selling cost (%)', min_value=0.0, max_value=0.12, value=0.05, step=0.005, format='%.3f')
    with c2:
        arv      = st.number_input('After-repair value (ARV)', min_value=10000, value=410000, step=5000)
        carry    = st.number_input('Carrying cost (total)', min_value=0, value=8450, step=250)
        hold_months = st.number_input('Base hold (months)', min_value=1.0, value=4.0, step=0.5)
    permit_days = st.slider('Permit delay (days)', 0, 120, 45)
    tax_drag = st.slider('Tax drag (annual % on purchase)', 0.0, 0.05, 0.022, step=0.001)
    sims_mode = st.radio('Simulation size', ['Quick (10k)','Full (100k)','Max (200k)'], index=2, horizontal=True)
    submitted = st.form_submit_button('Run simulations', use_container_width=True)

if submitted:
    st.header('2) Results')
    inp = {
      'address': html.escape(address), 'region_ring': region,
      'purchase': float(purchase), 'rehab': float(rehab), 'carry': float(carry),
      'selling_pct': float(selling_pct), 'projected_sale': float(arv),
      'hold_months': float(hold_months), 'permit_delay_days': int(permit_days),
      'tax_drag': float(tax_drag), 'ltv': 0.80, 'loan_rate_annual': 0.085
    }
    try:
        validate(inp, schema)
    except ValidationError as e:
        st.error(f'Input error: {e.message}'); st.stop()
    df = pd.DataFrame([inp])
    sims = 10000 if sims_mode.startswith('Quick') else 100000 if sims_mode.startswith('Full') else 200000

    with st.spinner('Simulating and auto-tuning…'):
        results, summaries, opps = run_all(df, regional_map, sims=sims, autotune=True)

    st.subheader('Decision bars (auto-tuned)'); st.json(summaries.get('bars', {}))
    st.subheader('Lens summaries'); st.json({'Engineer': summaries['Engineer'], 'Consumer': summaries['Consumer']})
    st.subheader('Opportunities (ranked)'); st.dataframe(opps, use_container_width=True)
    st.download_button('Download Opportunities CSV', data=opps.to_csv(index=False).encode('utf-8'), file_name='monetization_opportunities.csv', use_container_width=True)
    st.subheader('All results'); st.dataframe(results, use_container_width=True)
    st.download_button('Download All Results CSV', data=results.to_csv(index=False).encode('utf-8'), file_name='flip_results.csv', use_container_width=True)

    st.header('3) ChatGPT Handoff (free)')
    base_prompt = (
        f'PROPERTY: {address} in {region}\n'
        f'NUMBERS: purchase=${purchase:,.0f}, rehab=${rehab:,.0f}, carry=${carry:,.0f}, sell%={selling_pct:.1%}, ARV=${arv:,.0f}, '
        f'hold={hold_months}m, permit={permit_days}d, tax={tax_drag:.2%}\n'
        'TASK: Explain top risks and 3 actions to improve ROI for a novice Chicago agent, <=150 words.'
    )
    user_q = st.text_area('Ask a question (optional)', placeholder='What should I verify before offering?')
    st.text_area('Copy to ChatGPT', value=(user_q+'\n\n'+base_prompt) if user_q else base_prompt, height=160)
    st.link_button('Open ChatGPT', url='https://chat.openai.com', use_container_width=True)

st.caption('© 2025 Brian James Chapman — Realty Companion Pro – Chicago Edition • Licensed MIT')
