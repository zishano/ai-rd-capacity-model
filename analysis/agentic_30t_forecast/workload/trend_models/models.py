"""Small, nonseasonal candidate set. All horizons use actual calendar days."""
import json
import warnings

import numpy as np
from scipy.optimize import least_squares
from scipy.special import expit
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing

METHODS = ('naive', 'ols', 'piecewise', 'damped_holt', 'auto_arima')


def fit_predict(y, horizons, method, cap=None, half_life=None):
    y = np.asarray(y, dtype=float)
    h = np.asarray(horizons, dtype=int)
    x = np.arange(len(y), dtype=float)
    future = x[-1] + h
    scale = max(float(np.max(np.abs(y))), 1.) if method in ('damped_holt','auto_arima') else 1.
    y = y/scale
    parameters = {'internal_scale': scale}
    intervals = None
    if method == 'naive':
        values = np.full(len(h), y[-1])
    elif method in ('ols', 'piecewise'):
        design = np.column_stack((np.ones(len(x)), x))
        target = np.column_stack((np.ones(len(h)), future))
        if method == 'piecewise':
            # One hinge, each side >= 42 days. Penalize the change-point search.
            candidates = []
            for knot in range(42, len(y)-42, 7):
                a = np.column_stack((design, np.maximum(0, x-knot)))
                coef = np.linalg.lstsq(a, y, rcond=None)[0]
                rss = np.sum((y-a@coef)**2)
                candidates.append((len(y)*np.log(max(rss/len(y), 1e-20))+4*np.log(len(y)), knot))
            linear = np.linalg.lstsq(design, y, rcond=None)[0]
            linear_bic = len(y)*np.log(max(np.mean((y-design@linear)**2), 1e-20))+2*np.log(len(y))
            if candidates and min(candidates)[0] < linear_bic:
                _, knot = min(candidates)
                parameters['knot_day'] = knot
                design = np.column_stack((design, np.maximum(0, x-knot)))
                target = np.column_stack((target, np.maximum(0, future-knot)))
        coef = np.linalg.lstsq(design, y, rcond=None)[0]
        values = target@coef
        parameters['coefficients'] = coef.tolist()
    elif method == 'damped_holt':
        # Express damping bounds in days, making the frequency dependence explicit.
        bounds = (float(2**(-1/14)), float(2**(-1/730)))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            model = ExponentialSmoothing(y, trend='add', damped_trend=True, initialization_method='estimated',
                         bounds={'damping_trend': bounds})
            options = {} if half_life is None else {'damping_trend': 2**(-1/half_life)}
            fitted = model.fit(optimized=True, **options)
        values = np.asarray(fitted.forecast(int(max(h))))[h-1]
        parameters = {k: float(fitted.params[k]) for k in
                      ('smoothing_level','smoothing_trend','damping_trend','initial_level','initial_trend')}
        parameters['trend_half_life_days'] = float(-np.log(2)/np.log(parameters['damping_trend']))
        parameters['warnings'] = [str(w.message) for w in caught]
    elif method == 'auto_arima':
        best = None
        errors = []
        # Bounded AICc search, no annual or weekly seasonality.
        for d in (0, 1):
            for p, q in ((0,0),(1,0),(0,1),(1,1)):
                try:
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter('always')
                        fitted = ARIMA(y, order=(p,d,q), trend='ct' if d==0 else 't').fit()
                    if not fitted.mle_retvals.get('converged', True):
                        errors.append(f'{p},{d},{q}: nonconverged')
                        continue
                    if best is None or fitted.aicc < best[0]:
                        best = (fitted.aicc, fitted, (p,d,q), [str(w.message) for w in caught])
                except (ValueError, np.linalg.LinAlgError) as e:
                    errors.append(f'{p},{d},{q}: {e}')
        if best is None:
            raise ValueError('No converged ARIMA candidate: '+json.dumps(errors))
        score, fitted, order, notices = best
        prediction = fitted.get_forecast(int(max(h)))
        values = np.asarray(prediction.predicted_mean)[h-1]
        intervals = np.asarray(prediction.conf_int(alpha=.05))[h-1]
        parameters = dict(order=order, aicc=float(score), coefficients=fitted.params.tolist(),
                          rejected=errors, warnings=notices)
    elif method in ('logistic', 'gompertz'):
        if cap is None or cap <= max(y):
            raise ValueError('Conditional cap must exceed the observed maximum')
        def curve(t, a, rate):
            z = np.clip(a-rate*t, -50, 50)
            return cap*expit(-z) if method=='logistic' else cap*np.exp(-np.exp(z))
        fitted = least_squares(lambda v: (curve(x,*v)-y)/cap,
                               [2., .01], bounds=([-30.,0.],[30.,1.]))
        values = curve(future,*fitted.x)
        parameters = dict(cap=float(cap), a=float(fitted.x[0]), rate_per_day=float(fitted.x[1]),
                          jacobian_condition=float(np.linalg.cond(fitted.jac)), cap_basis='conditional sensitivity')
    else:
        raise ValueError(method)
    values = values * scale
    if intervals is not None:
        intervals = intervals * scale
    parameters['internal_scale'] = scale
    parameters['negative_forecasts_before_floor'] = int(np.sum(values < 0))
    parameters['fit_days'] = len(y)
    # Intervals remain raw Gaussian model intervals, exposing support violations.
    return np.maximum(0, values), parameters, intervals
