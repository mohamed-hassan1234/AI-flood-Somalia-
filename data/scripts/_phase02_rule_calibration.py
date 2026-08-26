import pandas as pd
from ml.common import fit_calibrator, metrics
from ml.pipeline import baseline_probability, partition

d = pd.read_csv('data/model_ready/food_security/food_security_dataset_v1.0.0.csv.gz')
d['target_period_start'] = pd.to_datetime(d['target_period_start'])
p = partition(d, 'food_security')
prevalence = p['train'].target.mean()
v = baseline_probability('food_security', p['validation'], prevalence)
t = baseline_probability('food_security', p['test'], prevalence)
c, info = fit_calibrator(p['validation'].target.to_numpy(), v)
print(info)
print('test identity', metrics(p['test'].target.to_numpy(), t, .5))
print('test calibrated', metrics(p['test'].target.to_numpy(), c.predict(t), .5))
