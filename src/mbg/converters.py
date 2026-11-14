"""Unfitted converter measurements in units of actual loaded VREF/2**bits.

These functions assess measurements, not their provenance. An ideal dataset
does not qualify a physical circuit; the AMS runner records that separately.
"""
from __future__ import annotations
import math


def _values(values, name):
    out = [float(v) for v in values]
    if not out or not all(math.isfinite(v) for v in out):
        raise ValueError(f'{name} must be nonempty finite numbers')
    return out


def _scale(bits, vref):
    if type(bits) is not int or not 1 <= bits <= 12:
        raise ValueError('bits must be integer 1..12')
    if not math.isfinite(vref) or vref<=0:
        raise ValueError('loaded VREF must be positive and finite')
    return 2**bits, float(vref)/2**bits


def _codes(values, n):
    out = _values(values, 'codes')
    if any(v != int(v) or not 0<=v<n for v in out):
        raise ValueError(f'codes must be integers 0..{n-1}')
    return [int(v) for v in out]


def dac_metrics(codes, voltages, *, vref, bits=4, limit_lsb=.5):
    n, lsb = _scale(bits,vref)
    cs = _codes(codes,n); vs = _values(voltages,'voltages')
    if len(cs)!=len(vs) or len(set(cs))!=len(cs):
        raise ValueError('one voltage per unique DAC code required')
    pairs = sorted(zip(cs,vs)); table = dict(pairs)
    missing = sorted(set(range(n))-set(cs))
    inl = {c:v/lsb-c for c,v in pairs}
    dnl = {c:(table[c]-table[c-1])/lsb-1 for c in range(1,n) if c in table and c-1 in table}
    monotonic = all(b[1]>a[1] for a,b in zip(pairs,pairs[1:]))
    mi = max(map(abs,inl.values())); md = max(map(abs,dnl.values()),default=float('inf'))
    return dict(status='PASS' if not missing and monotonic and mi<=limit_lsb+1e-12 and md<=limit_lsb+1e-12 else 'FAIL',
                bits=bits, vref_v=vref, lsb_v=lsb, missing_codes=missing, monotonic=monotonic,
                inl_lsb=inl, dnl_lsb=dnl, max_abs_inl_lsb=mi, max_abs_dnl_lsb=md,
                convention='absolute code*loaded_VREF/2**bits; no gain/offset fit')


def adc_metrics(vin, codes, *, vref, bits=4, limit_lsb=.5):
    n, lsb = _scale(bits,vref)
    xs = _values(vin,'vin'); cs = _codes(codes,n)
    if len(xs)!=len(cs) or len(xs)<2 or any(b<=a for a,b in zip(xs,xs[1:])):
        raise ValueError('ascending distinct VIN and one code per input are required')
    missing = sorted(set(range(n))-set(cs))
    monotonic = all(b>=a for a,b in zip(cs,cs[1:]))
    transitions = []
    intervals = []
    for k in range(1,n):
        hits = [i for i in range(1,len(xs)) if cs[i-1]<k<=cs[i]]
        if len(hits)!=1:
            transitions.append(None); continue
        i = hits[0]
        transitions.append((xs[i-1]+xs[i])/2)
        intervals.append((xs[i]-xs[i-1])/lsb)
    resolution = max(intervals,default=float('inf'))
    inl = [None if t is None else t/lsb-k for k,t in enumerate(transitions,1)]
    edges = [0.0,*transitions,vref]
    dnl = [None if a is None or b is None else (b-a)/lsb-1 for a,b in zip(edges,edges[1:])]
    mi = max((abs(v) for v in inl if v is not None),default=float('inf'))
    md = max((abs(v) for v in dnl if v is not None),default=float('inf'))
    covered = xs[0]<=0 and xs[-1]>=vref and cs[0]==0 and cs[-1]==n-1
    if missing or not monotonic or any(t is None for t in transitions):
        status = 'FAIL'
    elif mi-resolution/2>limit_lsb or md-resolution>limit_lsb:
        status = 'FAIL'
    elif not covered or resolution>.1+1e-12 or mi+resolution/2>limit_lsb+1e-12 or md+resolution>limit_lsb+1e-12:
        status = 'PARTIAL'
    else:
        status = 'PASS'
    return dict(status=status,bits=bits,vref_v=vref,lsb_v=lsb,missing_codes=missing,
                monotonic=monotonic,transitions_v=transitions,inl_lsb=inl,dnl_lsb=dnl,
                max_abs_inl_lsb=mi,max_abs_dnl_lsb=md,resolution_lsb=resolution,
                endpoint_coverage=covered,
                convention='transitions k*loaded_VREF/2**bits; endpoint clipping; no fit')


def settling_metrics(time, voltage, *, target, tolerance, deadline):
    ts = _values(time,'time'); vs = _values(voltage,'voltage')
    if len(ts)!=len(vs) or any(b<=a for a,b in zip(ts,ts[1:])):
        raise ValueError('ascending time and one voltage per sample required')
    if not all(math.isfinite(v) for v in (target,tolerance,deadline)) or tolerance<=0:
        raise ValueError('finite target/deadline and positive tolerance required')
    bad = [i for i,v in enumerate(vs) if abs(v-target)>tolerance]
    index = max(bad,default=-1)+1
    settled = ts[index] if index<len(ts) else None
    return dict(status='PASS' if settled is not None and settled<=deadline and ts[-1]>=deadline else 'FAIL',
                settling_s=settled,deadline_s=deadline,final_error_v=vs[-1]-target)


def transition_interval_metrics(intervals,*,bits=4,limit_lsb=.5):
    """Conservative INL/DNL bounds from verified dynamic threshold brackets.

    Inputs are absolute VIN/(loaded_VREF/2**bits), with no gain/offset fit.
    Callers must separately prove each bracket by real conversion results.
    """
    n,unused=_scale(bits,1.0)
    values=[tuple(_values(x,'transition interval')) for x in intervals]
    if len(values)!=n-1 or any(len(x)!=2 or not 0<=x[0]<x[1]<=n for x in values):
        raise ValueError('one finite ordered interval per transition required')
    mi=max(max(abs(lo-k),abs(hi-k)) for k,(lo,hi) in enumerate(values,1))
    edges=[(0,0),*values,(n,n)]
    dnl=[(b[0]-a[1]-1,b[1]-a[0]-1) for a,b in zip(edges,edges[1:])]
    md=max(max(map(abs,x)) for x in dnl)
    return dict(status='PASS' if mi<=limit_lsb+1e-12 and md<=limit_lsb+1e-12 else 'FAIL',
                max_abs_inl_bound_lsb=mi,max_abs_dnl_bound_lsb=md,
                transition_intervals_lsb=values,dnl_intervals_lsb=dnl,
                scope='mathematical bounds; dynamic bracket verification is a separate gate')
