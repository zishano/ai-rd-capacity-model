"""Calendar-day time axis; the last four years are extrapolation scenarios."""
from dataclasses import dataclass, asdict
from datetime import date
from math import exp, sqrt
from statistics import mean

from .observations import ROOT, series


def line(x, y):
    xm, ym = mean(x), mean(y)
    b = sum((i-xm)*(j-ym) for i,j in zip(x,y)) / sum((i-xm)**2 for i in x)
    return ym-b*xm, b


@dataclass
class Fit:
    method: str
    origin: date
    intercept: float
    slope: float
    knot: float = 0
    slope_change: float = 0
    ceiling: float = 0

    def predict(self, day):
        t = (day-self.origin).days
        value = self.intercept+self.slope*t
        if self.ceiling and t > self.knot:
            start = self.intercept+self.slope*self.knot
            gap = self.ceiling-start
            return self.ceiling-gap*exp(-self.slope*(t-self.knot)/gap)
        return value+self.slope_change*max(0,t-self.knot)


def fit(obs, method, ceiling=0):
    origin = obs[0][0]
    if method in ('last56','last84'):
        cutoff = obs[-1][0].toordinal()-int(method[4:])+1
        obs = [(d,v) for d,v in obs if d.toordinal()>=cutoff]
    x = [(d-origin).days for d,_ in obs]
    y = [v for _,v in obs]
    a,b = line(x,y)
    result = Fit(method,origin,a,b)
    if method == 'piecewise':
        # Continuous hinge at the pre-specified temporal midpoint; regress out 1 and t.
        knot = (x[0]+x[-1])/2
        h = [max(0,t-knot) for t in x]
        ah,bh = line(x,h)
        residual = [v-ah-bh*t for t,v in zip(x,h)]
        delta = sum(r*(v-a-b*t) for r,v,t in zip(residual,y,x))/sum(r*r for r in residual)
        result = Fit(method,origin,a-delta*ah,b-delta*bh,knot,delta)
    elif method == 'nonnegative':
        # Exact least squares on the cone a >= 0, b >= 0 (t >= 0).
        candidates = [(mean(y),0),(0,max(0,sum(t*v for t,v in zip(x,y))/sum(t*t for t in x)))]
        if a>=0 and b>=0:
            candidates.append((a,b))
        result.intercept,result.slope = min(candidates,key=lambda ab:sum((v-ab[0]-ab[1]*t)**2 for t,v in zip(x,y)))
    elif method == 'bounded':
        if ceiling <= a+b*x[-1] or b<=0:
            raise ValueError('Saturation comparison requires a positive slope and headroom')
        result.knot,result.ceiling = x[-1],ceiling
    elif method not in ('ols','last56','last84'):
        raise ValueError(method)
    return result


def diagnostics(model, obs, ceiling):
    training = obs[:-28]
    held = fit(training,model.method,ceiling)
    test = obs[-28:]
    errors = [held.predict(d)-v for d,v in test]
    center = mean(v for _,v in obs)
    return dict(**asdict(model), r2_full_window=1-sum((model.predict(d)-v)**2 for d,v in obs)/
                sum((v-center)**2 for _,v in obs), holdout_28d_mae=mean(abs(e) for e in errors),
                holdout_28d_rmse=sqrt(mean(e*e for e in errors)))


def legacy_projection(settings):
    obs = series(ROOT/settings['observations'],'agent_workdays_per_researcher_day')
    model = fit(obs,'ols')
    ref = date.fromisoformat(settings['reference_date'])
    baseline = model.predict(ref)
    projections = {}
    for year in settings['projection_years']:
        target = ref.replace(year=year)
        value = model.predict(target)
        if min(baseline,value)<=0:
            raise ValueError('Nonpositive fitted workload')
        projections[str(year)] = dict(date=target.isoformat(), observations=len(obs), fit_start=obs[0][0].isoformat(),
            fit_end=obs[-1][0].isoformat(),intercept=model.intercept,slope_per_day=model.slope,
            agent_workdays_per_researcher_day=value,usage_multiplier=value/baseline)
    return projections
