"""Conditional predictive distributions on spaced rolling-window observations.

These are distributions of the published smoothed targets, not raw daily traffic.
Gaussian latent draws are censored at zero; their mass at zero is reported explicitly.
"""
import warnings

import numpy as np
from scipy.special import softmax
from statsmodels.tsa.statespace.structural import UnobservedComponents

METHODS = ('naive_rw', 'ols_spaced', 'local_level', 'local_linear', 'damped_local_linear', 'ensemble')
COMPONENTS = ('naive_rw', 'ols_spaced', 'damped_local_linear')


def spaced(y, stride):
    """Anchor the sampling grid at the forecast origin; never use future values."""
    return np.asarray(y, dtype=float)[np.arange(len(y)-1, -1, -stride)[::-1]]


def normal_draws(mean, covariance, n, rng):
    eigenvalues, vectors = np.linalg.eigh((covariance+covariance.T)/2)
    if np.min(eigenvalues) < -1e-6:
        raise ValueError('Materially non-positive-semidefinite covariance')
    return mean + rng.standard_normal((n,len(mean))) @ (vectors*np.sqrt(np.maximum(eigenvalues,0))).T


def forecast(y, stride, horizons, method, draws=2400, seed=20261122, half_life=365):
    sample=spaced(y,stride)
    if len(sample)<4:
        raise ValueError('At least four spaced observations required')
    h=np.asarray(horizons,float)
    nsteps=int(np.ceil(max(h)/stride))
    if method=='ensemble':
        fitted=[forecast(y,stride,h,m,draws,seed+i*103,half_life) for i,m in enumerate(COMPONENTS)]
        return np.concatenate([v[0] for v in fitted]),dict(method=method,components=list(COMPONENTS),weights=[1/3]*3,
                    component_parameters={m:v[1] for m,v in zip(COMPONENTS,fitted)},
                    effective_points=len(sample),stride_days=stride,
                    basis='equal-weight mixture of conditional predictive distributions, not calibrated coverage')
    rng=np.random.default_rng(seed)
    scale=max(float(np.max(abs(sample))),1.)
    z=sample/scale
    info=dict(method=method,effective_points=len(z),stride_days=stride,scale=scale,
              few_points_warning=len(z)<12,interpolation='linear between window-spaced forecasts')
    if method=='naive_rw':
        variance=float(np.mean(np.diff(z)**2))
        future=z[-1]+np.cumsum(rng.normal(0,np.sqrt(variance),(draws,nsteps)),axis=1)
        info['innovation_variance']=variance
    elif method=='ols_spaced':
        x=np.column_stack([np.ones(len(z)),np.arange(len(z))])
        beta=np.linalg.lstsq(x,z,rcond=None)[0]
        df=len(z)-2
        s2=float(np.sum((z-x@beta)**2)/df)
        conditional_variance=s2*df/rng.chisquare(df,draws)
        beta_draws=normal_draws(beta,np.linalg.inv(x.T@x),draws,rng)
        beta_draws=beta+(beta_draws-beta)*np.sqrt(conditional_variance[:,None])
        fx=np.column_stack([np.ones(nsteps),np.arange(len(z),len(z)+nsteps)])
        future=beta_draws@fx.T+rng.normal(size=(draws,nsteps))*np.sqrt(conditional_variance[:,None])
        info.update(coefficients=beta.tolist(),residual_variance=s2,degrees_of_freedom=df,
                    basis='Student-t linear regression predictive sampling on spaced observations')
    else:
        kind='local level' if method=='local_level' else 'local linear trend'
        model=UnobservedComponents(z,level=kind)
        if method=='damped_local_linear':
            phi=2**(-stride/half_life)
            model.ssm['transition']=np.array([[1.,phi],[0.,phi]])
            info.update(half_life_days=half_life,half_life_basis='conditional assumption',phi=phi)
        attempts=[]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            for optimizer in ('lbfgs','powell'):
                result=model.fit(method=optimizer,disp=False,maxiter=500)
                attempts.append(dict(optimizer=optimizer,converged=bool(result.mle_retvals.get('converged',True))))
                if attempts[-1]['converged']:
                    break
        if not attempts[-1]['converged']:
            raise ValueError(f'No converged state-space fit: {attempts}')
        info.update(parameters=dict(zip(result.param_names,map(float,result.params))),attempts=attempts,
                    warnings=[str(w.message) for w in caught],
                    basis='Gaussian state/observation simulation conditional on fitted noise variances; no parameter uncertainty')
        ssm=model.ssm
        transition=ssm['transition']
        process=ssm['selection']@ssm['state_cov']@ssm['selection'].T
        obs=ssm['design'][0]
        obs_var=max(0.,float(ssm['obs_cov'][0,0]))
        states=normal_draws(result.predicted_state[:,-1],result.predicted_state_cov[:,:,-1],draws,rng)
        future=np.empty((draws,nsteps))
        for k in range(nsteps):
            future[:,k]=states@obs+rng.normal(0,np.sqrt(obs_var),draws)
            states=states@transition.T+normal_draws(np.zeros(len(obs)),process,draws,rng)
    grid=np.arange(nsteps+1)*stride
    raw=np.column_stack([np.full(draws,z[-1]),future])*scale
    interpolated=np.array([np.interp(h,grid,path) for path in raw])
    info['negative_latent_fraction']=float(np.mean(interpolated<0))
    return np.maximum(0,interpolated),info


def composition(days, shares, future, method='composition_rw', draws=2400, seed=20261122,
                half_life=365, shrinkage=.5, floor=.0005):
    """Joint logistic-normal paths, with uncertainty in all nine shares together."""
    selected=[len(days)-1]
    for i in range(len(days)-2,-1,-1):
        if (days[selected[-1]]-days[i]).days>=28:
            selected.append(i)
    selected=selected[::-1]
    if len(selected)<4:
        raise ValueError('Too few spaced composition observations')
    values=np.maximum(np.asarray(shares)[selected],floor)
    values/=values.sum(axis=1,keepdims=True)
    clr=np.log(values);clr-=clr.mean(axis=1,keepdims=True)
    times=np.array([(days[i]-days[selected[0]]).days for i in selected],float)
    increments=np.diff(clr,axis=0)/np.sqrt(np.diff(times))[:,None]
    covariance=np.cov(increments,rowvar=False)
    covariance=(1-shrinkage)*covariance+shrinkage*np.diag(np.diag(covariance))
    projection=np.eye(9)-np.ones((9,9))/9
    covariance=projection@covariance@projection
    trend=np.polyfit(times,clr,1)[0] if method=='composition_damped' else np.zeros(9)
    offsets=np.array([(d-days[-1]).days for d in future])
    decay=np.log(2)/half_life
    rng=np.random.default_rng(seed)
    state=np.tile(clr[-1],(draws,1))
    paths=[];centers=[];previous=0
    for h in offsets:
        drift=trend*(np.exp(-decay*previous)-np.exp(-decay*h))/decay
        state+=drift+normal_draws(np.zeros(9),covariance*(h-previous),draws,rng)
        paths.append(softmax(state,axis=1))
        centers.append(softmax(clr[-1]+trend*(1-np.exp(-decay*h))/decay))
        previous=h
    return np.stack(paths,axis=1),np.array(centers),dict(method=method,effective_points=len(selected),
         sample_dates=[days[i].isoformat() for i in selected],zero_floor=floor,shrinkage=shrinkage,
         half_life_days=half_life,clr_slope_per_day=trend.tolist(),covariance_per_day=covariance.tolist(),
         basis='conditional logistic-normal joint paths; shrinkage/floor/half-life assumed; no raw researcher counts')


def legacy_concurrency_bands(days, shares, future, draws=2400, seed=20261122, block_days=28):
    """Preserve the original dual-threshold center; bootstrap its paired trend residuals.

    This estimates conditional trend-fit uncertainty, not calibrated predictive coverage.
    Both thresholds use the same residual blocks to retain their dependence.
    """
    from ..run import bin_predict
    shares=np.asarray(shares,float)
    shares=shares/shares.sum(axis=1,keepdims=True)
    center=bin_predict(days,shares,future,'legacy_log_complement')
    x=np.array([(d-days[0]).days for d in days],float)
    design=np.column_stack([np.ones(len(x)),x])
    target=np.log1p(-np.column_stack([shares[:,4:].sum(1),shares[:,6:].sum(1)]))
    coefficient=np.linalg.lstsq(design,target,rcond=None)[0]
    residual=target-design@coefficient
    residual-=residual.mean(axis=0)
    starts=np.array([i for i in range(len(days)-block_days+1)
                     if (days[i+block_days-1]-days[i]).days==block_days-1])
    if not len(starts):raise ValueError('No contiguous calendar block available for bootstrap')
    rng=np.random.default_rng(seed)
    chosen=rng.choice(starts,size=(draws,int(np.ceil(len(days)/block_days))))
    indices=(chosen[:,:,None]+np.arange(block_days)).reshape(draws,-1)[:,:len(days)]
    sampled_coefficients=coefficient+np.einsum('kn,dnj->dkj',np.linalg.pinv(design),residual[indices])
    future_design=np.column_stack([np.ones(len(future)),[(d-days[0]).days for d in future]])
    log_complements=np.einsum('hk,dkj->dhj',future_design,sampled_coefficients)
    probability=-np.expm1(np.clip(log_complements,-745,0))
    violating=probability[:,:,1]>probability[:,:,0]
    probability[:,:,1]=np.minimum(probability[:,:,1],probability[:,:,0])
    groups=[shares[-1,:4],shares[-1,4:6],shares[-1,6:]]
    masses=[1-probability[:,:,0],probability[:,:,0]-probability[:,:,1],probability[:,:,1]]
    paths=np.concatenate([mass[:,:,None]*group/group.sum() for mass,group in zip(masses,groups)],axis=2)
    metadata=dict(center_method='legacy_log_complement',center_unchanged=True,
        uncertainty_method='paired moving-calendar-block residual bootstrap of the two original trends',
        seed=seed,draws=draws,block_days=block_days,valid_block_starts=len(starts),
        coefficients=coefficient.tolist(),nested_projection_fraction=float(violating.mean()),
        probability_floor_fraction=float(np.mean(log_complements>0)),
        limitation='trend-fit uncertainty only; few independent blocks; no four-year calibrated coverage')
    return paths,center,metadata
