"""Metrics from measured converter data; no circuit synthesis or optimization."""
from mbg.agent.envelope import Result


def adc(args, ctx):
    from mbg.converters import adc_metrics
    metrics = adc_metrics(args['vin'], args['codes'], bits=args['bits'], vref=args['vref'])
    result = Result(tool='measure.adc')
    result.metrics = metrics
    return result.set(metrics['status'], 'ADC transition metrics evaluated')


def dac(args, ctx):
    from mbg.converters import dac_metrics
    metrics = dac_metrics(args['codes'], args['voltages'], bits=args.get('bits') or 4, vref=args['vref'])
    result = Result(tool='measure.dac')
    result.metrics = metrics
    return result.set(metrics['status'], 'DAC code metrics evaluated')
