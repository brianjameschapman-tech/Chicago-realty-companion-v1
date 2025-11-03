# Realty Companion Pro – Chicago Edition
# © 2025 Brian James Chapman. All Rights Reserved.
# Licensed under the MIT License – see LICENSE file for details.
import json
import numpy as np, pandas as pd
from pathlib import Path

def load_json(p, default):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return default

def headwind_index(region, regional_map):
    r = regional_map['rings'].get(region, next(iter(regional_map['rings'].values())))
    inv=r['inventory_months']; dom=r['dom_days']; ls=r['list_sale_ratio']; tax=r['tax_rate']; permit=r['permit_delay_days']
    inv_n=min(inv/6.0,1.0); dom_n=min(dom/60.0,1.0); tax_n=min(tax/0.025,1.0); permit_n=min(permit/60.0,1.0)
    hi=100.0*(0.30*inv_n+0.25*dom_n+0.20*(1.0-ls)+0.15*tax_n+0.10*permit_n)
    return float(np.clip(hi,0.0,100.0))

def gaussian_copula_normals(rng, n, R):
    Z = rng.standard_normal((n,R.shape[0]))
    L = np.linalg.cholesky(R + 1e-12*np.eye(R.shape[0]))
    return Z @ L.T

def cvar5_empirical(roi):
    p5 = np.percentile(roi,5)
    tail = roi[roi<=p5]
    return float(tail.mean()) if tail.size>0 else float(p5)

def simulate_once(df, regional_map, sims, lens, rng=None):
    if rng is None: rng=np.random.default_rng()
    rows=[]
    R=np.array([[1.0,-0.35,0.20],[-0.35,1.0,0.15],[0.20,0.15,1.0]])
    Z=gaussian_copula_normals(rng,sims,R)
    regimes=np.array([0.2,0.6,0.2]) if lens=='Engineer' else np.array([0.15,0.6,0.25])
    idx=rng.choice([0,1,2],size=sims,p=regimes)
    arv_shift=np.array([-0.03,0.0,0.02])[idx]
    hold_shift=np.array([0.6,0.0,-0.3])[idx]
    rehab_sd,arv_sd,hold_sd=(0.30,0.15,1.40) if lens=='Engineer' else (0.15,0.08,0.70)

    for _,r in df.iterrows():
        region=str(r['region_ring']); hi=headwind_index(region,regional_map)
        purchase=float(r['purchase']); rehab=float(r['rehab']); carry=float(r['carry']); selling=float(r['selling_pct']); arv=float(r['projected_sale'])
        hold_m=float(r.get('hold_months',4)); permit=float(r.get('permit_delay_days',0)); tax=float(r.get('tax_drag',0.02))
        ltv=float(r.get('ltv',0.8)); rate=float(r.get('loan_rate_annual',0.085))
        z_arv,z_hold,z_rehab=Z[:,0],Z[:,1],Z[:,2]
        rehab_draw=np.exp(np.log(max(rehab,1.0))+rehab_sd*z_rehab)
        sale_draw=np.clip(arv*(1.0+arv_sd*z_arv+arv_shift),0.5*purchase,None)
        hold_draw=np.clip(hold_m+permit/30.0+hold_sd*z_hold+hold_shift,1.0,None)
        loan_amt=ltv*purchase; interest_cost=loan_amt*rate*(hold_draw/12.0)
        sell_cost=np.clip(selling,0.0,0.12)*sale_draw; carry_total=(carry/max(1.0,hold_m))*hold_draw
        tax_drag_amt=tax*purchase*(hold_draw/12.0)
        tpc=purchase+rehab_draw+carry_total+interest_cost+tax_drag_amt+sell_cost
        roi=(sale_draw-tpc)/tpc
        p_loss=float((roi<0).mean()); p5,p10,p50,p90=np.percentile(roi,[5,10,50,90]); cvar5=cvar5_empirical(roi)
        risk_adj=(1.0-hi/100.0)*p50
        rows.append({'address':r['address'],'region_ring':region,'HI':round(hi,1),
                     'P10_ROI%':round(100*p10,2),'P50_ROI%':round(100*p50,2),'P90_ROI%':round(100*p90,2),
                     'VaR5_ROI%':round(100*p5,2),'CVaR5_ROI%':round(100*cvar5,2),'P(loss)%':round(100*p_loss,2),
                     'Risk-Adj ROI P50%':round(100*risk_adj,2)})
    return pd.DataFrame(rows)

def decide(df,bars=None):
    if bars is None: bars={'risk_adj':8.5,'ploss':15.0,'cvar':-10.0}
    r=float(df['Risk-Adj ROI P50%'].median()); p=float(df['P(loss)%'].median()); c=float(df['CVaR5_ROI%'].median())
    return {'RiskAdj':r,'Ploss':p,'CVaR5':c,'Status':'GO' if (r>=bars['risk_adj'] and p<=bars['ploss'] and c>bars['cvar']) else 'CAUTION'}

def autotune_bars(cons_df, cons_sum, opp_df, opp_sum, defaults={'risk_adj':8.5,'ploss':15.0,'cvar':-10.0}):
    cand_r=np.arange(6.0,12.5,0.5); cand_p=np.arange(10.0,25.5,0.5); cand_c=np.arange(-20.0,-5.0,1.0)
    def go_rate(df,b):
        return float(((df['Risk-Adj ROI P50%']>=b['risk_adj']) & (df['P(loss)%']<=b['ploss']) & (df['CVaR5_ROI%']>b['cvar'])).mean())
    best=defaults; best_score=-1
    for rr in cand_r:
        for pp in cand_p:
            for cc in cand_c:
                b={'risk_adj':float(rr),'ploss':float(pp),'cvar':float(cc)}
                ge=go_rate(cons_df,b); gc=go_rate(opp_df,b)
                pen = 0.0 if ge<=0.15 else -5.0*(ge-0.15)
                reward = 1.0 - abs(gc-0.33)
                safety = (cc+20.0)/10.0
                score = reward + safety + pen
                if score>best_score:
                    best_score=score; best=b
    return best

def run_all(df, regional_map, sims=200000, bars=None, autotune=True, save_path='data/auto_tune.json'):
    eng=simulate_once(df, regional_map, sims=sims, lens='Engineer'); eng['lens']='Engineer'
    con=simulate_once(df, regional_map, sims=sims, lens='Consumer'); con['lens']='Consumer'
    both=pd.concat([eng,con], ignore_index=True)
    defaults={'risk_adj':8.5,'ploss':15.0,'cvar':-10.0}
    if bars is None: bars=defaults
    sums={'Engineer':decide(eng,bars),'Consumer':decide(con,bars),'bars':bars}
    if autotune:
        tuned=autotune_bars(eng, sums['Engineer'], con, sums['Consumer'], defaults)
        sums={'Engineer':decide(eng,tuned),'Consumer':decide(con,tuned),'bars':tuned,'defaults':defaults}
        try:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_path).write_text(json.dumps(tuned, indent=2))
        except Exception:
            pass
    grp=both.groupby(['region_ring','lens'], as_index=False).median(numeric_only=True)
    rows=[]; b=sums['bars']
    for _,row in grp.iterrows():
        status='GO' if (row['Risk-Adj ROI P50%']>=b['risk_adj'] and row['P(loss)%']<=b['ploss'] and row['CVaR5_ROI%']>b['cvar']) else 'CAUTION'
        nudge='Pursue comps & financing quotes now' if status=='GO' else 'Renegotiate price 5–10% or trim rehab 10–15%'
        rows.append({'region':row['region_ring'],'lens':row['lens'],'RiskAdj%':row['Risk-Adj ROI P50%'],'Ploss%':row['P(loss)%'],'CVaR5%':row['CVaR5_ROI%'],'status':status,'nudge':nudge})
    opps=pd.DataFrame(rows).sort_values(['status','RiskAdj%'], ascending=[True,False])
    return both, sums, opps
