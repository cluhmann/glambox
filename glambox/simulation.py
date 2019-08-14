#!/usr/bin/python

import numpy as np
import pandas as pd
from scipy.stats import invgauss
from tqdm import tqdm


def simulate_subject(parameters,
                     values,
                     gaze,
                     n_repeats=1,
                     subject=0,
                     boundary=1,
                     error_weight=0.05,
                     error_range=(0, 5000)):
    n_trials, n_items = values.shape

    rts = np.zeros(n_trials * n_repeats) * np.nan
    choices = np.zeros(n_trials * n_repeats) * np.nan
    trial_idx = np.zeros(n_trials * n_repeats) * np.nan
    repeat_idx = np.zeros(n_trials * n_repeats) * np.nan

    running_idx = 0

    for trial in range(n_trials):
        for repeat in range(n_repeats):

            choice, rt = simulate_trial(parameters,
                                        values[trial],
                                        gaze[trial],
                                        boundary=boundary,
                                        error_weight=error_weight,
                                        error_range=error_range)

            rts[running_idx] = rt
            choices[running_idx] = choice
            trial_idx[running_idx] = trial
            repeat_idx[running_idx] = repeat

            running_idx += 1

    df = pd.DataFrame(
        dict(subject=np.ones(n_trials * n_repeats) * subject,
             trial=trial_idx,
             repeat=repeat_idx,
             choice=choices,
             rt=rts))

    for i in range(n_items):
        df['item_value_{}'.format(i)] = np.repeat(values[:, i], n_repeats)
        df['gaze_{}'.format(i)] = np.repeat(gaze[:, i], n_repeats)

    return df


def simulate_trial(parameters,
                   values,
                   gaze,
                   boundary=1,
                   error_weight=0.05,
                   error_range=(0, 5)):
    """
    Simulate GLAM for a single trial.

    Args:
        parameters (tuple): v, gamma, s, tau and t0 parameters
        values (np.ndarray): array of item values
        gaze (np.ndarray): array of gaze towards items (should sum to 1)
        boundary (float, optional): decision boundary, defaults to 1.0
        error_weight (float, optional): probability of simulating random choice from error model
        error_range (tuple, optional): range of response times used by error model

    Returns:
        int, float: choice, response time

    """
    v, gamma, s, tau, t0 = parameters
    n_items = len(values)

    if np.random.uniform(0, 1) < error_weight:
        rt = np.random.uniform(*error_range)
        choice = np.random.choice(n_items)

    else:
        rt = np.nan
        while np.isnan(rt):
            R = make_R(v, tau, gamma, values, gaze)
            FPTs = np.zeros(n_items) * np.nan

            for i in range(n_items):
                mu = boundary / R[i]
                lam = (boundary / s)**2
                FPTs[i] = invgauss.rvs(mu=mu / lam, scale=lam)
            rt = np.min(FPTs)

            if rt < 0 or not np.isfinite(rt):
                rt = np.nan
                choice = np.nan
            else:
                choice = np.argmin(FPTs)
                rt = rt + t0

    return choice, rt


def make_R(v, tau, gamma, values, gaze):
    n_items = len(values)

    A = gaze * values + (1. - gaze) * gamma * values
    R_star = np.zeros(n_items)

    for i in range(n_items):
        others = np.arange(n_items)[np.arange(n_items) != i].astype(int)
        R_star[i] = A[i] - np.max(A[others])

    R = v / (1 + np.exp(-tau * R_star))

    return R


def predict(model, n_repeats=1, boundary=1., error_weight=0.05, verbose=True):
    """
    Generates GLAM predictions for a given (fitted) model.
    Predictions for every trial are repeated `n_repeats` time.
    The generating model is a mixture between an error model
    and GLAM. `error_weight` determines the mixture weight of
    the error component.
    """

    prediction = pd.DataFrame()

    subjects = np.unique(model.data['subject'])

    value_cols = ['item_value_{}'.format(i) for i in range(model.n_items)]
    gaze_cols = ['gaze_{}'.format(i) for i in range(model.n_items)]

    if not verbose:
        row_iterator = range(model.data.shape[0])
    else:
        row_iterator = tqdm(range(model.data.shape[0]))
        print(
            'Generating predictions for {} trials ({} repeats each)...'.format(
                model.data.shape[0], n_repeats))
    for row_index in row_iterator:

        row = model.data.iloc[row_index, :]

        subject = row['subject']
        trial = row['trial']
        subject_estimates = model.estimates[model.estimates['subject'] ==
                                            subject]
        # Get the right parameter estimates for the trial
        parameters = np.zeros(5) * np.nan
        for p, parameter in enumerate(['v', 'gamma', 's', 'tau', 't0']):
            dependence = model.depends_on.get(parameter)
            if dependence is not None:
                condition = row[model.depends_on[parameter]]
                parameters[
                    p] = subject_estimates.loc[subject_estimates[dependence] ==
                                               condition, parameter].head(1)
            else:
                parameters[p] = subject_estimates[parameter].head(1).values

        # Compute error RT range
        rt_min = model.data['rt'][model.data['subject'] ==
                                  subject].values.min()
        rt_max = model.data['rt'][model.data['subject'] ==
                                  subject].values.max()
        error_range = (rt_min, rt_max)

        values = row[value_cols].values
        gaze = row[gaze_cols].values

        for r in range(n_repeats):
            choice, rt = simulate_trial(parameters=parameters,
                                        values=values,
                                        gaze=gaze,
                                        boundary=boundary,
                                        error_weight=error_weight,
                                        error_range=error_range)
            pred_row = row.copy()
            pred_row['choice'] = choice
            pred_row['rt'] = rt
            pred_row['repeat'] = r

            prediction = prediction.append(pred_row, ignore_index=True)

    return prediction
