"""
Generate techflow_financials.csv for the demo simulation.
Run this script once to create the dataset, then upload it as a scene data file.
"""
import pandas as pd
import numpy as np

np.random.seed(42)
months = pd.date_range('2024-07-01', periods=18, freq='MS')

data = {
    'date': months,
    'month_number': range(1, 19),
}

# MRR starts at $45K, grows ~8% MoM with noise
mrr = [45000]
for i in range(17):
    growth = np.random.normal(0.08, 0.02)
    mrr.append(mrr[-1] * (1 + growth))
data['mrr'] = [round(m, 2) for m in mrr]
data['arr'] = [round(m * 12, 2) for m in mrr]

# Customers start at 120, grow with MRR
customers = [120]
for i in range(17):
    new = np.random.randint(8, 18)
    churned = np.random.randint(2, 6)
    customers.append(customers[-1] + new - churned)
data['customers'] = customers

# Churn rate ~3-5%
data['churn_rate'] = [round(np.random.uniform(0.03, 0.055), 4) for _ in range(18)]

# Revenue (MRR + some services revenue)
data['revenue'] = [round(m * 1.12, 2) for m in mrr]

# COGS ~25% of revenue
data['cogs'] = [round(r * np.random.uniform(0.22, 0.28), 2) for r in data['revenue']]

# Operating costs: starts at $210K, grows slowly (hiring)
op_costs = [210000]
for i in range(17):
    op_costs.append(round(op_costs[-1] * np.random.uniform(1.01, 1.03), 2))
data['operating_costs'] = op_costs

# Cash balance: starts at $2.1M, decreases by (op_costs + cogs - revenue) each month
cash = [2100000]
for i in range(17):
    net = data['revenue'][i] - data['cogs'][i] - data['operating_costs'][i]
    cash.append(round(cash[-1] + net, 2))
data['cash_balance'] = cash

df = pd.DataFrame(data)
df.to_csv('/Users/hendrikkrack/Desktop/n-aible/n-aible-worktrees/daytona-sandbox/scripts/techflow_financials.csv', index=False)
print(df.to_string())
print(f"\nLatest MRR: ${mrr[-1]:,.0f}")
print(f"Latest burn: ${data['operating_costs'][-1] + data['cogs'][-1] - data['revenue'][-1]:,.0f}/mo")
print(f"Current cash: ${cash[-1]:,.0f}")
print(f"Approx runway: {cash[-1] / (data['operating_costs'][-1] + data['cogs'][-1] - data['revenue'][-1]):.1f} months")
