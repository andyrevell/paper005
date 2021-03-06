"""
2020.05.06
Ankit Khambhati, updated by Andy Revell

Purpose:
Function pipelines for filtering time-varying data

Logic of code:
    1. Common average reference (common_avg_ref)
    2. Fit an AR(1) model to the data and retains the residual as the pre-whitened data (ar_one)
    3. bandpass, lowpass, highpass filtering (Notch at 60Hz, HPF at 5Hz, LPF at 115Hz, XCorr at 0.25) (elliptic)
    4. Calculate cross-correlation similarity function for functional connectivity (xcorr_mag)
    5. Calculate a band-specific functional network, coherence. (multitaper)

Table of Contents:
A. Main
    1. broadband_conn
    2. multiband_conn
B. Supporting Code:
    3. common_avg_ref
    4. ar_one
    5. elliptic
    6. xcorr_mag
    7. xcorr
C. Utilities
    8. check_path
    9. make_path
    10. check_path_overwrite
    11. check_has_key
    12. check_dims
    13. check_type
    14. check_function

See individual function comments for inputs and outputs

Change Log
----------
2016/12/11 - Implemented broadband_conn
2020/05/06 - updated code to work with python 3.7, numpy 1.18.4, scipy 1.4.1, mtspec 0.3.2. Added header to python code above
    Added note how to install mtsepc below.
"""

from __future__ import division
import numpy as np
import os
import inspect
from scipy import signal as signal
#from mtspec import mt_coherence
from scipy.stats import pearsonr, spearmanr
#from scipy import stats
#from sklearn.feature_selection import mutual_info_classif
#from sklearn.metrics import mutual_info_score, normalized_mutual_info_score
from sklearn.feature_selection import mutual_info_regression
import time

import matplotlib.pyplot as plt
import seaborn as sns

#%%
""""
Note 2020.05.06
To install mtspec:
See https://krischer.github.io/mtspec/ for more documentation
1. Need to have gfortran installed on computer
2. It is different for Linux and Mac

Linux:
#apt-get install gfortran
#pip install mtspec

#or
# conda config --add channels conda-forge
# conda install mtspec

Mac OS:
Need homebrew, then do:
#brew install gcc
#brew cask install gfortran
#pip install mtspec
"""

"""
A. Main
"""
# Parameter set
#Bands
param_band = {}
param_band['Broadband'] = [1., 127.]
param_band['delta'] = [1., 4.]
param_band['theta'] = [4., 8.]
param_band['alpha'] = [8., 13.]
param_band['beta'] = [13., 30.]
param_band['gammaLow'] = [30., 40.]
param_band['gammaMid'] = [70., 100.]
param_band['gammaHigh'] = [100., 127.]

#Filters
param = {}
g = 1.0
gpass = 1.0 #changed from 0.1 to 1 because seems like 0.1 does not work for notch filter. Do not use 2.0 --> does not work for delta band. 1.0 seems good
gstop = 60.0
param['Notch_60Hz'] = {'wp': [58.0, 62.0],
                       'ws': [59.0, 61.0],
                       'gpass': gpass,
                       'gstop': gstop}
param['Broadband'] = {'wp': param_band['Broadband'],
                    'ws': [ param_band['Broadband'][0]-0.5 , param_band['Broadband'][1]+0.5  ],
                    'gpass': gpass,
                    'gstop': gstop}
param['delta'] = {'wp': param_band['delta'],
                    'ws': [ param_band['delta'][0]-0.5 , param_band['delta'][1]+g  ],
                    'gpass': gpass,
                    'gstop': gstop}
param['theta'] = {'wp': param_band['theta'],
                    'ws': [ param_band['theta'][0]-g , param_band['theta'][1]+g  ],
                    'gpass': gpass,
                    'gstop': gstop}
param['alpha'] = {'wp': param_band['alpha'],
                    'ws': [ param_band['alpha'][0]-g , param_band['alpha'][1]+g  ],
                    'gpass': gpass,
                    'gstop': gstop}
param['beta'] = {'wp': param_band['beta'],
                    'ws': [ param_band['beta'][0]-g , param_band['beta'][1]+g  ],
                    'gpass': gpass,
                    'gstop': gstop}
param['gammaLow'] = {'wp': param_band['gammaLow'],
                    'ws': [ param_band['gammaLow'][0]-g , param_band['gammaLow'][1]+g  ],
                    'gpass': gpass,
                    'gstop': gstop}
param['gammaMid'] = {'wp': param_band['gammaMid'],
                    'ws': [ param_band['gammaMid'][0]-g , param_band['gammaMid'][1]+g  ],
                    'gpass': gpass,
                    'gstop': gstop}
param['gammaHigh'] = {'wp': param_band['gammaHigh'],
                    'ws': [ param_band['gammaHigh'][0]-g , param_band['gammaHigh'][1]+0.5  ],
                    'gpass': gpass,
                    'gstop': gstop}
param['XCorr'] = {'tau': 0.5}



"""
n_samp, n_chan = data.shape
start = 0
stop = 1

adj_crossCorrelation_all = crossCorrelation_wrapper(data[range(start, fs*stop), :], fs, param, avgref=True)
plot_adj_allbands(adj_crossCorrelation_all, vmin = -0.7, vmax = 0.9)

adj_pearson_all, adj_pearson_all_pval = pearson_wrapper(data[range(start, fs*stop), :], fs, param, avgref=True)
plot_adj_allbands(adj_pearson_all, vmin = -0.7, vmax = 0.9)
plot_adj_allbands(adj_pearson_all_pval, vmin = 0, vmax = 0.05/((n_chan*n_chan-n_chan)/2)    )


adj_spearman_all, adj_spearman_all_pval = spearman_wrapper(data[range(start, fs*stop), :], fs, param, avgref=True)
plot_adj_allbands(adj_spearman_all, vmin = -0.7, vmax = 0.9)
plot_adj_allbands(adj_spearman_all_pval, vmin = 0, vmax = 0.05/((n_chan*n_chan-n_chan)/2)   )


adj_coherence_all = coherence_wrapper(data[range(start, fs*stop), :], fs, param, avgref=True)
plot_adj_allbands(adj_coherence_all, vmin = 0, vmax = 1 )


adj_mi_all = mutualInformation_wrapper(data[range(start, fs*stop), :], fs, param, avgref=True)
plot_adj_allbands(adj_mi_all, vmin = 0, vmax = 1 )

"""


#%%
#Wrapper scripts
def crossCorrelation_wrapper(data, fs, param = param, avgref=True):
    """
    Pipeline function for computing a broadband functional network from ECoG.

    See: Khambhati, A. N. et al. (2015).
    Dynamic Network Drivers of Seizure Generation, Propagation and Termination in
    Human Neocortical Epilepsy. PLOS Computational Biology, 11(12).

    Data --> CAR Filter --> Notch Filter --> Band-pass Filter --> Cross-Correlation

    Parameters
    ----------
        data: ndarray, shape (T, N)
            Input signal with T samples over N variates

        fs: int
            Sampling frequency

        reref: True/False
            Re-reference data to the common average (default: True)

    Returns
    -------
        adj: ndarray, shape (N, N)
            Adjacency matrix for N variates
    """

    # Standard param checks
    check_type(data,np.ndarray)
    check_dims(data, 2)
    check_type(fs, int)

    # Build pipeline
    if avgref:
        data_ref = common_avg_ref(data)
    else:
        data_ref = data.copy()
    data_ref_ar = ar_one(data_ref)

    data_bb, data_d, data_t, data_a, data_b, data_gl, data_gm, data_gh = elliptic_bandFilter(data_ref_ar, fs, param)
    
    print("Cross Correlation Broadband")
    adj_xcorr_bb = crossCorrelation_connectivity(data_bb, fs, **param['XCorr'], absolute=False)
    print("Cross Correlation Delta")
    adj_xcorr_d = crossCorrelation_connectivity(data_d, fs, **param['XCorr'], absolute=False)
    print("Cross Correlation Theta")
    adj_xcorr_t = crossCorrelation_connectivity(data_t, fs, **param['XCorr'], absolute=False)
    print("Cross Correlation Alpha")
    adj_xcorr_a = crossCorrelation_connectivity(data_a, fs, **param['XCorr'], absolute=False)
    print("Cross Correlation Beta")
    adj_xcorr_b = crossCorrelation_connectivity(data_b, fs, **param['XCorr'], absolute=False)
    print("Cross Correlation Gamma - Low")
    adj_xcorr_gl = crossCorrelation_connectivity(data_gl, fs, **param['XCorr'], absolute=False)
    print("Cross Correlation Gamma - Mid")
    adj_xcorr_gm = crossCorrelation_connectivity(data_gm, fs, **param['XCorr'], absolute=False)
    print("Cross Correlation Gamma - High")
    adj_xcorr_gh = crossCorrelation_connectivity(data_gh, fs, **param['XCorr'], absolute=False)

    return adj_xcorr_bb, adj_xcorr_d, adj_xcorr_t, adj_xcorr_a, adj_xcorr_b, adj_xcorr_gl, adj_xcorr_gm, adj_xcorr_gh
      

def pearson_wrapper(data, fs, param = param, avgref=True):
    """
    Parameters
    ----------
        data: ndarray, shape (T, N)
            Input signal with T samples over N variates

        fs: int
            Sampling frequency

        reref: True/False
            Re-reference data to the common average (default: True)

    Returns
    -------
        adj: ndarray, shape (N, N)
            Adjacency matrix for N variates
    """

    # Standard param checks
    check_type(data,np.ndarray)
    check_dims(data, 2)
    check_type(fs, int)

    # Build pipeline
    if avgref:
        data_ref = common_avg_ref(data)
    else:
        data_ref = data.copy()
    data_ref_ar = ar_one(data_ref)

    data_bb, data_d, data_t, data_a, data_b, data_gl, data_gm, data_gh = elliptic_bandFilter(data_ref_ar, fs, param)
    
    print("Pearson Correlation Broadband")
    adj_pearson_bb, adj_pearson_bb_pval  = pearson_connectivity(data_bb, fs)
    print("Pearson Correlation Delta")
    adj_pearson_d, adj_pearson_d_pval = pearson_connectivity(data_d, fs)
    print("Pearson Correlation Theta")
    adj_pearson_t, adj_pearson_t_pval = pearson_connectivity(data_t, fs)
    print("Pearson Correlation Alpha")
    adj_pearson_a, adj_pearson_a_pval = pearson_connectivity(data_a, fs)
    print("Pearson Correlation Beta")
    adj_pearson_b, adj_pearson_b_pval = pearson_connectivity(data_b, fs)
    print("Pearson Correlation Gamma - Low")
    adj_pearson_gl, adj_pearson_gl_pval = pearson_connectivity(data_gl, fs)
    print("Pearson Correlation Gamma - Mid")
    adj_pearson_gm, adj_pearson_gm_pval = pearson_connectivity(data_gm, fs)
    print("Pearson Correlation Gamma - High")
    adj_pearson_gh, adj_pearson_gh_pval = pearson_connectivity(data_gh, fs)

    return [adj_pearson_bb, adj_pearson_d, adj_pearson_t, adj_pearson_a, adj_pearson_b, adj_pearson_gl, adj_pearson_gm, adj_pearson_gh], [adj_pearson_bb_pval, adj_pearson_d_pval, adj_pearson_t_pval, adj_pearson_a_pval, adj_pearson_b_pval, adj_pearson_gl_pval, adj_pearson_gm_pval, adj_pearson_gh_pval]


      
def spearman_wrapper(data, fs, param = param, avgref=True):
    """
    Parameters
    ----------
        data: ndarray, shape (T, N)
            Input signal with T samples over N variates

        fs: int
            Sampling frequency

        reref: True/False
            Re-reference data to the common average (default: True)

    Returns
    -------
        adj: ndarray, shape (N, N)
            Adjacency matrix for N variates
    """

    # Standard param checks
    check_type(data,np.ndarray)
    check_dims(data, 2)
    check_type(fs, int)

    # Build pipeline
    if avgref:
        data_ref = common_avg_ref(data)
    else:
        data_ref = data.copy()
    data_ref_ar = ar_one(data_ref)

    data_bb, data_d, data_t, data_a, data_b, data_gl, data_gm, data_gh = elliptic_bandFilter(data_ref_ar, fs, param)
    
    print("spearman Correlation Broadband")
    adj_spearman_bb, adj_spearman_bb_pval  = spearman_connectivity(data_bb, fs)
    print("spearman Correlation Delta")
    adj_spearman_d, adj_spearman_d_pval = spearman_connectivity(data_d, fs)
    print("spearman Correlation Theta")
    adj_spearman_t, adj_spearman_t_pval = spearman_connectivity(data_t, fs)
    print("spearman Correlation Alpha")
    adj_spearman_a, adj_spearman_a_pval = spearman_connectivity(data_a, fs)
    print("spearman Correlation Beta")
    adj_spearman_b, adj_spearman_b_pval = spearman_connectivity(data_b, fs)
    print("spearman Correlation Gamma - Low")
    adj_spearman_gl, adj_spearman_gl_pval = spearman_connectivity(data_gl, fs)
    print("spearman Correlation Gamma - Mid")
    adj_spearman_gm, adj_spearman_gm_pval = spearman_connectivity(data_gm, fs)
    print("spearman Correlation Gamma - High")
    adj_spearman_gh, adj_spearman_gh_pval = spearman_connectivity(data_gh, fs)

    return [adj_spearman_bb, adj_spearman_d, adj_spearman_t, adj_spearman_a, adj_spearman_b, adj_spearman_gl, adj_spearman_gm, adj_spearman_gh], [adj_spearman_bb_pval, adj_spearman_d_pval, adj_spearman_t_pval, adj_spearman_a_pval, adj_spearman_b_pval, adj_spearman_gl_pval, adj_spearman_gm_pval, adj_spearman_gh_pval]
      
    
 
def coherence_wrapper(data, fs, param = param, avgref=True):
    
    """
    Pipeline function for computing a band-specific functional network from ECoG.

    See: Khambhati, A. N. et al. (2016).
    Virtual Cortical Resection Reveals Push-Pull Network Control
    Preceding Seizure Evolution. Neuron, 91(5).

    Data --> CAR Filter --> Multi-taper Coherence

    Parameters
    ----------
        data: ndarray, shape (T, N)
            Input signal with T samples over N variates

        fs: int
            Sampling frequency

        reref: True/False
            Re-reference data to the common average (default: True)

    Returns
    -------
        adj_alphatheta: ndarray, shape (N, N)
            Adjacency matrix for N variates (Alpha/Theta Band 5-15 Hz)

        adj_beta: ndarray, shape (N, N)
            Adjacency matrix for N variates (Beta Band 15-25 Hz)

        adj_lowgamma: ndarray, shape (N, N)
            Adjacency matrix for N variates (Low Gamma Band 30-40 Hz)

        adj_highgamma: ndarray, shape (N, N)
            Adjacency matrix for N variates (High Gamma Band 95-105 Hz)
    """

    # Standard param checks
    check_type(data, np.ndarray)
    check_dims(data, 2)
    check_type(fs, int)

    # Build pipeline
    if avgref:
        data_ref = common_avg_ref(data)
    else:
        data_ref = data.copy()
    data_ref_60 = elliptic(data_ref, fs, **param['Notch_60Hz'])
    
    print("Coherence Broadband")
    band = "Broadband"
    adj_coherence_bb = coherence_connectivity(data_ref_60, fs, param[band]['wp'])
    print("Coherence Delta")
    band = "delta"
    adj_coherence_d = coherence_connectivity(data_ref_60, fs, param[band]['wp'])
    print("Coherence Theta")
    band = "theta"
    adj_coherence_t = coherence_connectivity(data_ref_60, fs, param[band]['wp'])
    print("Coherence Alpha")
    band = "alpha"
    adj_coherence_a = coherence_connectivity(data_ref_60, fs, param[band]['wp'])
    print("Coherence Beta")
    band = "beta"
    adj_coherence_b = coherence_connectivity(data_ref_60, fs, param[band]['wp'])
    print("Coherence Gamma - Low")
    band = "gammaLow"
    adj_coherence_gl = coherence_connectivity(data_ref_60, fs, param[band]['wp'])
    print("Coherence Gamma - Mid")
    band = "gammaMid"
    adj_coherence_gm = coherence_connectivity(data_ref_60, fs, param[band]['wp'])
    print("Coherence Gamma - High")
    band = "gammaHigh"
    adj_coherence_gh = coherence_connectivity(data_ref_60, fs, param[band]['wp'])

    return adj_coherence_bb, adj_coherence_d, adj_coherence_t, adj_coherence_a, adj_coherence_b, adj_coherence_gl, adj_coherence_gm, adj_coherence_gh
    
    
    
    
def mutualInformation_wrapper(data, fs, param = param, avgref=True):
    """
    Pipeline function for computing a broadband functional network from ECoG.

    See: Khambhati, A. N. et al. (2015).
    Dynamic Network Drivers of Seizure Generation, Propagation and Termination in
    Human Neocortical Epilepsy. PLOS Computational Biology, 11(12).

    Data --> CAR Filter --> Notch Filter --> Band-pass Filter --> Cross-Correlation

    Parameters
    ----------
        data: ndarray, shape (T, N)
            Input signal with T samples over N variates

        fs: int
            Sampling frequency

        reref: True/False
            Re-reference data to the common average (default: True)

    Returns
    -------
        adj: ndarray, shape (N, N)
            Adjacency matrix for N variates
    """

    # Standard param checks
    check_type(data,np.ndarray)
    check_dims(data, 2)
    check_type(fs, int)

    # Build pipeline
    if avgref:
        data_ref = common_avg_ref(data)
    else:
        data_ref = data.copy()
    data_ref_ar = ar_one(data_ref)

    data_bb, data_d, data_t, data_a, data_b, data_gl, data_gm, data_gh = elliptic_bandFilter(data_ref_ar, fs, param)
    
    print("Mutual Information Broadband")
    adj_mi_bb = mutualInformation_connectivity(data_bb, fs)
    print("Mutual Information Delta")
    adj_mi_d = mutualInformation_connectivity(data_d, fs)
    print("Mutual Information Theta")
    adj_mi_t = mutualInformation_connectivity(data_t, fs)
    print("Mutual Information Alpha")
    adj_mi_a = mutualInformation_connectivity(data_a, fs)
    print("Mutual Information Beta")
    adj_mi_b = mutualInformation_connectivity(data_b, fs)
    print("Mutual Information Gamma - Low")
    adj_mi_gl = mutualInformation_connectivity(data_gl, fs)
    print("Mutual Information Gamma - Mid")
    adj_mi_gm = mutualInformation_connectivity(data_gm, fs)
    print("Mutual Information Gamma - High")
    adj_mi_gh = mutualInformation_connectivity(data_gh, fs)

    return adj_mi_bb, adj_mi_d, adj_mi_t, adj_mi_a, adj_mi_b, adj_mi_gl, adj_mi_gm, adj_mi_gh
          
    
    
    
    
    
    
    
    
    
    
#%%
    
    
    
def pearson_connectivity(data, fs):

    # Retrieve data attributes
    n_samp, n_chan = data.shape

    n_samp, n_chan = data.shape
    triu_ix, triu_iy = np.triu_indices(n_chan, k=1)

    # Initialize adjacency matrix
    adj = np.zeros((n_chan, n_chan))
    adj_pvalue = np.zeros((n_chan, n_chan))

    # Compute all coherences
    count = 0
    for n1, n2 in zip(triu_ix, triu_iy):
        t0 = time.time()
        adj[n1, n2] = pearsonr(  data[:,n1], data[:,n2])[0]
        adj_pvalue[n1, n2] = pearsonr(  data[:,n1], data[:,n2])[1]
        t1= time.time(); td = t1-t0; tr = td*(len(triu_ix)-count)/60; printProgressBar(count+1, len(triu_ix), prefix = '', suffix = f"{count}  {np.round(tr,2)} min", decimals = 1, length = 20, fill = "X", printEnd = "\r"); count = count+1

    adj += adj.T
    adj_pvalue += adj_pvalue.T
    return adj, adj_pvalue

def spearman_connectivity(data, fs):
    
    # Retrieve data attributes
    n_samp, n_chan = data.shape

    n_samp, n_chan = data.shape
    triu_ix, triu_iy = np.triu_indices(n_chan, k=1)

    # Initialize adjacency matrix
    adj = np.zeros((n_chan, n_chan))
    adj_pvalue = np.zeros((n_chan, n_chan))
    
    # Compute all coherences
    count = 0
    for n1, n2 in zip(triu_ix, triu_iy):
        t0 = time.time()
        adj[n1, n2] = spearmanr(  data[:,n1], data[:,n2])[0]
        adj_pvalue[n1, n2] = spearmanr(  data[:,n1], data[:,n2])[1]
        t1= time.time(); td = t1-t0; tr = td*(len(triu_ix)-count)/60; printProgressBar(count+1, len(triu_ix), prefix = '', suffix = f"{count}  {np.round(tr,2)} min", decimals = 1, length = 20, fill = "X", printEnd = "\r"); count = count+1
    adj += adj.T
    adj_pvalue += adj_pvalue.T
    return adj, adj_pvalue

def crossCorrelation_connectivity(data_hat, fs, tau, absolute=False):
    """
    The xcorr_mag function implements a cross-correlation similarity function
    for computing functional connectivity -- maximum magnitude cross-correlation

    This function implements an FFT-based cross-correlation (using convolution).

    Parameters
    ----------
        data_hat: ndarray, shape (T, N)
            Input signal with T samples over N variates

        fs: int
            Sampling frequency

        tau: float
            The max lag limits of cross-correlation in seconds

    Returns
    -------
        adj: ndarray, shape (N, N)
            Adjacency matrix for N variates
    """

    # Standard param checks
    check_type(data_hat, np.ndarray)
    check_dims(data_hat, 2)
    check_type(fs, int)
    check_type(tau, float)

    # Get data_hat attributes
    n_samp, n_chan = data_hat.shape
    tau_samp = int(tau*fs)
    triu_ix, triu_iy = np.triu_indices(n_chan, k=1)

    # Normalize the signal
    data_hat -= data_hat.mean(axis=0)
    data_hat /= data_hat.std(axis=0)

    # Initialize adjacency matrix
    adj = np.zeros((n_chan, n_chan))
    lags = np.hstack((range(0, n_samp, 1),
                      range(-n_samp, 0, 1)))
    tau_ix = np.flatnonzero(np.abs(lags) <= tau_samp)

    # Use FFT to compute cross-correlation
    data_hat_fft = np.fft.rfft( np.vstack((data_hat, np.zeros_like(data_hat))), axis=0)

    # Iterate over all edges
    count = 0
    for n1, n2 in zip(triu_ix, triu_iy):
        t0 = time.time()
        xc = 1 / n_samp * np.fft.irfft( data_hat_fft[:, n1] * np.conj(data_hat_fft[:, n2]))
        if absolute==True:
            adj[n1, n2] = np.max( np.abs(xc[tau_ix])  )
        #taking the absolute max value, whether negative or positive, but preserving sign
        elif absolute==False:
            if xc[tau_ix].max() > np.abs(xc[tau_ix].min()):
                adj[n1, n2] = xc[tau_ix].max()
            else:
                adj[n1, n2] = xc[tau_ix].min()
        t1= time.time(); td = t1-t0; tr = td*(len(triu_ix)-count)/60; printProgressBar(count+1, len(triu_ix), prefix = '', suffix = f"{count}  {np.round(tr,2)} min", decimals = 1, length = 20, fill = "X", printEnd = "\r"); count = count+1
    adj += adj.T

    return adj

   


def mutualInformation_connectivity(data_hat, fs):
    #https://www.roelpeters.be/calculating-mutual-information-in-python/
    #https://scikit-learn.org/stable/modules/generated/sklearn.feature_selection.mutual_info_regression.html#id6
    
    
    # Retrieve data_hat attributes
    n_samp, n_chan = data_hat.shape

    n_samp, n_chan = data_hat.shape
    triu_ix, triu_iy = np.triu_indices(n_chan, k=1)

    # Initialize adjacency matrix
    adj = np.zeros((n_chan, n_chan))

    # Compute all coherences
    count = 0
    for n1, n2 in zip(triu_ix, triu_iy):
        t0 = time.time()
        #METHOD 1 - wrong. Need to treat continuous variable (time series EEG) differently. MI is for classes
        #adj[n1, n2] = normalized_mutual_info_score(  data_hat[:,n1], data_hat[:,n2])
        
        #METHOD 2 - better
        #c_xy = np.histogram2d( data_hat[:,n1],  data_hat[:,n2], 1000)[0]  
        #adj[n1, n2] = mutual_info_score( None, None, contingency=c_xy)
        
        #METHOD 3 - best
        adj[n1, n2] = mutual_info_regression( data_hat[:,n1].reshape(-1,1), data_hat[:,n2], n_neighbors=3  ) #Note: Very slow
        t1= time.time(); td = t1-t0; tr = td*(len(triu_ix)-count)/60; printProgressBar(count+1, len(triu_ix), prefix = '', suffix = f"{count}  {np.round(tr,2)} min", decimals = 1, length = 20, fill = "X", printEnd = "\r"); count = count+1
    adj += adj.T
    return adj

def coherence_connectivity(data_hat, fs, cf):
    """
    The multitaper function windows the signal using multiple Slepian taper
    functions and then computes coherence between windowed signals.

    Parameters
    ----------
        data_hat: ndarray, shape (T, N)
            Input signal with T samples over N variates

        fs: int
            Sampling frequency

        time_band: float
            The time half bandwidth resolution of the estimate [-NW, NW];
            such that resolution is 2*NW

        n_taper: int
            Number of Slepian sequences to use (Usually < 2*NW-1)

        cf: list
            Frequency range over which to compute coherence [-NW+C, C+NW]

    Returns
    -------
        adj: ndarray, shape (N, N)
            Adjacency matrix for N variates
    """

    # Standard param checks
    check_type(data_hat, np.ndarray)
    check_dims(data_hat, 2)
    check_type(cf, list)

    if not len(cf) == 2:
        raise Exception('Must give a frequency range in list of length 2')

    # Get data_hat attributes
    n_samp, n_chan = data_hat.shape
    triu_ix, triu_iy = np.triu_indices(n_chan, k=1)

    # Initialize adjacency matrix
    adj = np.zeros((n_chan, n_chan))

    # Compute all coherences
    count = 0
    for n1, n2 in zip(triu_ix, triu_iy):
        t0 = time.time()
        if (data_hat[:, n1] == data_hat[:, n2]).all():
            adj[n1, n2] = np.nan
        else:
            out = signal.coherence(x= data_hat[:, n1],
                                   y = data_hat[:, n2],
                                   fs = fs,
                                   window= range(int(fs-fs/3)) #if n_samp = fs, the window has to be less than fs, or else you will get output as all ones. So I modified to be fs - -fs/3, and not just fs
                                   )

            # Find closest frequency to the desired center frequency
            cf_idx = np.flatnonzero((out[0] >= cf[0]) &
                                    (out[0] <= cf[1]))

            # Store coherence in association matrix
            adj[n1, n2] = np.mean(out[1][cf_idx])
        t1= time.time(); td = t1-t0; tr = td*(len(triu_ix)-count)/60; printProgressBar(count+1, len(triu_ix), prefix = '', suffix = f"{count}  {np.round(tr,2)} min", decimals = 1, length = 20); count = count+1

    adj += adj.T

    return adj    
    



   

"""

def multitaper(data, fs, time_band, n_taper, cf):
    
    The multitaper function windows the signal using multiple Slepian taper
    functions and then computes coherence between windowed signals.

    Parameters
    ----------
        data: ndarray, shape (T, N)
            Input signal with T samples over N variates

        fs: int
            Sampling frequency

        time_band: float
            The time half bandwidth resolution of the estimate [-NW, NW];
            such that resolution is 2*NW

        n_taper: int
            Number of Slepian sequences to use (Usually < 2*NW-1)

        cf: list
            Frequency range over which to compute coherence [-NW+C, C+NW]

    Returns
    -------
        adj: ndarray, shape (N, N)
            Adjacency matrix for N variates
            
            
    param_cohe['time_band'] = 5.
    param_cohe['n_taper'] = 9
    

    # Standard param checks
    check_type(data, np.ndarray)
    check_dims(data, 2)
    check_type(time_band, float)
    check_type(n_taper, int)
    check_type(cf, list)
    if n_taper >= 2*time_band:
        raise Exception('Number of tapers must be less than 2*time_band')
    if not len(cf) == 2:
        raise Exception('Must give a frequency range in list of length 2')

    # Get data attributes
    n_samp, n_chan = data.shape
    triu_ix, triu_iy = np.triu_indices(n_chan, k=1)

    # Initialize adjacency matrix
    adj = np.zeros((n_chan, n_chan))

    # Compute all coherences
    count = 0
    for n1, n2 in zip(triu_ix, triu_iy):
        t0 = time.time()
        if (data[:, n1] == data[:, n2]).all():
            adj[n1, n2] = np.nan
        else:
            out = mt_coherence(1.0/fs,
                               data[:, n1],
                               data[:, n2],
                               time_band,
                               n_taper,
                               int(n_samp/2.), 0.95,
                               iadapt=1,
                               cohe=True, freq=True)

            # Find closest frequency to the desired center frequency
            cf_idx = np.flatnonzero((out['freq'] >= cf[0]) &
                                    (out['freq'] <= cf[1]))

            # Store coherence in association matrix
            adj[n1, n2] = np.mean(out['cohe'][cf_idx])
        t1= time.time(); td = t1-t0; tr = td*(len(triu_ix)-count)/60; printProgressBar(count+1, len(triu_ix), prefix = '', suffix = f"{count}  {np.round(tr,2)} min", decimals = 1, length = 20, fill = "X", printEnd = "\r"); count = count+1

    adj += adj.T

    return adj
"""
#%%
"""
B. Referencing and Filters
"""


def common_avg_ref(data):
    """
    The common_avg_ref function subtracts the common mode signal from the original
    signal. Suggested for removing correlated noise, broadly over a sensor array.

    Parameters
    ----------
        data: ndarray, shape (T, N)
            Input signal with T samples over N variates

    Returns
    -------
        data_reref: ndarray, shape (T, N)
            Referenced signal with common mode removed
    """
    # Standard param checks
    check_type(data, np.ndarray)
    check_dims(data, 2)
    # Remove common mode signal
    data_reref = (data.T - data.mean(axis=1)).T
    return data_reref


def ar_one(data):
    """
    The ar_one function fits an AR(1) model to the data and retains the residual as
    the pre-whitened data

    Parameters
    ----------
        data: ndarray, shape (T, N)
            Input signal with T samples over N variates

    Returns
    -------
        data_white: ndarray, shape (T, N)
            Whitened signal with reduced autocorrelative structure
    """
    
    # Standard param checks
    check_type(data, np.ndarray)
    check_dims(data, 2)
    # Retrieve data attributes
    n_samp, n_chan = data.shape
    # Apply AR(1)
    data_white = np.zeros((n_samp-1, n_chan))
    for i in range(n_chan):
        win_x = np.vstack((data[:-1, i], np.ones(n_samp-1)))
        w = np.linalg.lstsq(win_x.T, data[1:, i], rcond=None)[0]
        data_white[:, i] = data[1:, i] - (data[:-1, i]*w[0] + w[1])
    return data_white


def elliptic(data_hat, fs, wp, ws, gpass, gstop):
    """
    The elliptic function implements bandpass, lowpass, highpass filtering

    This implements zero-phase filtering to pre-process and analyze
    frequency-dependent network structure. Implements Elliptic IIR filter.

    Parameters
    ----------
        data_hat: ndarray, shape (T, N)
            Input signal with T samples over N variates

        fs: int
            Sampling frequency

        wp: tuple, shape: (1,) or (1,1)
            Pass band cutoff frequency (Hz)

        ws: tuple, shape: (1,) or (1,1)
            Stop band cutoff frequency (Hz)

        gpass: float
            Pass band maximum loss (dB)

        gstop: float
            Stop band minimum attenuation (dB)

    Returns
    -------
        data_hat_filt: ndarray, shape (T, N)
            Filtered signal with T samples over N variates
    """

    # Standard param checks
    check_type(data_hat, np.ndarray)
    check_dims(data_hat, 2)
    check_type(fs, int)
    check_type(wp, list)
    check_type(ws, list)
    check_type(gpass, float)
    check_type(gstop, float)
    if not len(wp) == len(ws):
        raise Exception('Frequency criteria mismatch for wp and ws')
    if not (len(wp) < 3):
        raise Exception('Must only be 1 or 2 frequency cutoffs in wp and ws')

    # Design filter
    nyq = fs / 2.0

    # new code. Works with scipy 1.4 (2020.05.06)
    wpass_nyq = [iter*0 for iter in range(len(wp))]
    for m in range(0, len(wp)):
        wpass_nyq[m] = wp[m] / nyq

    # new code. Works with scipy 1.4 (2020.05.06)
    wstop_nyq = [iter*0 for iter in range(len(ws))]
    for m in range(0, len(ws)):
        wstop_nyq[m] = ws[m] / nyq

    #wpass_nyq = map(lambda f: f/nyq, wp) #old code. Works with scipy 0.18
    #wstop_nyq = map(lambda f: f/nyq, wstop) #old code. Works with scipy 0.18
    b, a = signal.iirdesign(wp=wpass_nyq,
                                     ws=wstop_nyq,
                                     gpass=gpass,
                                     gstop=gstop,
                                     ftype='ellip')
    # Perform filtering and dump into signal_packet
    data_hat_filt = signal.filtfilt(b, a, data_hat, axis=0)
    return data_hat_filt


def elliptic_bandFilter(data, fs, param):
    
    data_60 = elliptic(data, fs, **param['Notch_60Hz']) 
    band = "Broadband"
    data_bb = elliptic(data_60, fs,  [param[band]['wp'][1]], [param[band]['ws'][1]], gpass,  gstop)
    data_bb = elliptic(data_bb, fs,  [param[band]['wp'][0]], [param[band]['ws'][0]], gpass,  gstop)

    band = "delta"
    data_d = elliptic(data_60, fs,  [param[band]['wp'][1]], [param[band]['ws'][1]], gpass,  gstop)
    data_d = elliptic(data_d, fs,  [param[band]['wp'][0]], [param[band]['ws'][0]], gpass,  gstop)
    
    band = "theta"
    data_t = elliptic(data_60, fs,  [param[band]['wp'][1]], [param[band]['ws'][1]], gpass,  gstop)
    data_t = elliptic(data_t, fs,  [param[band]['wp'][0]], [param[band]['ws'][0]], gpass,  gstop)
    
    band = "alpha"
    data_a = elliptic(data_60, fs,  [param[band]['wp'][1]], [param[band]['ws'][1]], gpass,  gstop)
    data_a = elliptic(data_a, fs,  [param[band]['wp'][0]], [param[band]['ws'][0]], gpass,  gstop)

    band = "beta"
    data_b = elliptic(data_60, fs,  [param[band]['wp'][1]], [param[band]['ws'][1]], gpass,  gstop)
    data_b = elliptic(data_b, fs,  [param[band]['wp'][0]], [param[band]['ws'][0]], gpass,  gstop)
    
    band = "gammaLow"
    data_gl = elliptic(data_60, fs,  [param[band]['wp'][1]], [param[band]['ws'][1]], gpass,  gstop)
    data_gl = elliptic(data_gl, fs,  [param[band]['wp'][0]], [param[band]['ws'][0]], gpass,  gstop)
    
    band = "gammaMid"
    data_gm = elliptic(data_60, fs,  [param[band]['wp'][1]], [param[band]['ws'][1]], gpass,  gstop)
    data_gm = elliptic(data_gm, fs,  [param[band]['wp'][0]], [param[band]['ws'][0]], gpass,  gstop)

    band = "gammaHigh"
    data_gh = elliptic(data_60, fs,  [param[band]['wp'][1]], [param[band]['ws'][1]], gpass,  gstop)
    data_gh = elliptic(data_gh, fs,  [param[band]['wp'][0]], [param[band]['ws'][0]], gpass,  gstop)

    return data_bb, data_d, data_t, data_a, data_b, data_gl, data_gm, data_gh


def butterworth_filt(data, fs):
    filtered = np.zeros(data.shape)
    w = np.array([1, 120])  / np.array([(fs / 2), (fs / 2)])  # Normalize the frequency
    b, a = signal.butter(4, w, 'bandpass')
    filtered = signal.filtfilt(b, a, data)
    for i in range(data.shape[1]): filtered[:, i] = signal.filtfilt(b, a, data[:, i])
    filtered = filtered + (data[0] - filtered[0])  # correcting offset created by filtfilt
    b, a = signal.iirnotch(60, 30, fs)
    notched = np.zeros(data.shape)
    for i in range(data.shape[1]): notched[:, i] = signal.filtfilt(b, a, filtered[:, i])
    
    return notched




#%%
"""
C. Utilities:
"""

def check_path(path):
    '''
    Check if path exists

    Parameters
    ----------
        path: str
            Check if valid path
    '''
    if not os.path.exists(path):
        raise IOError('%s does not exists' % path)


def make_path(path):
    '''
    Make new path if path does not exist

    Parameters
    ----------
        path: str
            Make the specified path
    '''
    if not os.path.exists(path):
        os.makedirs(path)
    else:
        raise IOError('Path: %s, already exists' % path)


def check_path_overwrite(path):
    '''
    Prevent overwriting existing path

    Parameters
    ----------
        path: str
            Check if path exists
    '''
    if os.path.exists(path):
        raise IOError('%s cannot be overwritten' % path)


def check_has_key(dictionary, key_ref):
    '''
    Check whether the dictionary has the specified key

    Parameters
    ----------
        dictionary: dict
            The dictionary to look through

        key_ref: str
            The key to look for
    '''
    if key_ref not in dictionary.keys():
        raise KeyError('%r should contain the %r key' % (dictionary, key_ref))


def check_dims(arr, nd):
    '''
    Check if numpy array has specific number of dimensions

    Parameters
    ----------
        arr: numpy.ndarray
            Input array for dimension checking

        nd: int
            Number of dimensions to check against
    '''
    if not arr.ndim == nd:
        raise Exception('%r has %r dimensions. Must have %r' % (arr, arr.ndim, nd))


def check_type(obj, typ):
    '''
    Check if obj is of correct type

    Parameters
    ----------
        obj: any
            Input object for type checking

        typ: type
            Reference object type (e.g. str, int)
    '''
    if not isinstance(obj, typ):
        raise TypeError('%r is %r. Must be %r' % (obj, type(obj), typ))


def check_function(obj):
    '''
    Check if obj is a function

    Parameters
    ----------
        obj: any
            Input object for type checking
    '''
    if not inspect.isfunction(obj):
        raise TypeError('%r must be a function.' % (obj))

# Progress bar function
def printProgressBar(iteration, total, prefix = '', suffix = '', decimals = 1, length = 100, fill = "X", printEnd = "\r"):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + '-' * (length - filledLength)
    print('\r%s |%s| %s%% %s' % (prefix, bar, percent, suffix), end = printEnd)
    # Print New Line on Complete
    if iteration == total:
        print()
        
        
def show_eeg_compare(data, data_hat, fs, channel = 0, start_sec = 0, stop_sec = 2):
    data_ch = data[:,channel]
    data_ch_hat = data_hat[:,channel]    
    fig,axes = plt.subplots(1,2,figsize=(8,4), dpi = 300)
    sns.lineplot(x =  np.array(range(fs*start_sec,fs*stop_sec))/1e6*fs, y = data_ch[range(fs*start_sec,fs*stop_sec)], ax = axes[0] , linewidth=0.5 )
    sns.lineplot(x =  np.array(range(fs*start_sec,fs*stop_sec))/1e6*fs, y = data_ch_hat[range(fs*start_sec,fs*stop_sec)] , ax = axes[1], linewidth=0.5 )
    plt.show()


def plot_adj(adj, vmin = -1, vmax = 1 ):
    fig,axes = plt.subplots(1,1,figsize=(4,4), dpi = 300)
    sns.heatmap(adj, square=True, ax = axes, vmin = vmin, vmax = vmax)

def plot_adj_allbands(adj_list, vmin = -1, vmax = 1, titles = ["Broadband", "Delta", "Theta", "Alpha", "Beta", "Gamma - Low", "Gamma - Mid", "Gamma - High"] ):
    fig,axes = plt.subplots(2,4,figsize=(16,9), dpi = 300)
    count = 0
    for x in range(2):
        for y in range(4):
            sns.heatmap(adj_list[count], square=True, ax = axes[x][y], vmin = vmin, vmax = vmax)
            axes[x][y].set_title(titles[count], size=10)
            count = count+1


#%%
#visulaize
"""
vmin = -0.5; vmax = 0.9; title_size = 8
fig,axes = plt.subplots(4,2,figsize=(8,16), dpi = 300)
sns.heatmap(adj_xcorr, square=True, ax = axes[0][0], vmin = vmin, vmax = vmax); axes[0][0].set_title("X corr; tau: 0.25 ; elliptic", size=title_size)
sns.heatmap(np.abs(adj_xcorr), square=True, ax = axes[0][1], vmin = 0, vmax = vmax); axes[0][1].set_title("X corr Abs; tau: 0.25; elliptic", size=title_size)
   

sns.heatmap(adj_pear, square=True, ax = axes[1][0], vmin = vmin, vmax = vmax); axes[1][0].set_title("Pearson; elliptic", size=title_size)
sns.heatmap(adj_spear, square=True, ax = axes[1][1], vmin = vmin, vmax = vmax); axes[1][1].set_title("Spearman; elliptic", size=title_size)
sns.heatmap(adj_cohe_bb_m, square=True, ax = axes[2][0]); axes[2][0].set_title("Coherence: mt_spec; elliptic", size=title_size)
sns.heatmap(adj_cohe_bb, square=True, ax = axes[2][1]); axes[2][1].set_title("Coherence: Scipy; elliptic", size=title_size)
   
sns.heatmap(adj_MI, square=True, ax = axes[3][0]); axes[3][0].set_title("Mutual Information; elliptic", size=title_size)



fig,axes = plt.subplots(2,2,figsize=(8,8), dpi = 300)
sns.heatmap(adj_butter_xcorr, square=True, ax = axes[0][0], vmin = vmin, vmax = vmax)
sns.heatmap(np.abs(adj_butter_xcorr), square=True, ax = axes[0][1], vmin = vmin, vmax = vmax)
sns.heatmap(adj_butter_pear, square=True, ax = axes[1][0], vmin = vmin, vmax = vmax)
sns.heatmap(adj_butter_spear, square=True, ax = axes[1][1], vmin = vmin, vmax = vmax)
###########
###########
###########
###########
ch = 1
data_ch = data[:,ch]
data_ch_hat = data_hat[:,ch]
  
fig,axes = plt.subplots(1,2,figsize=(8,4), dpi = 300)
st = 0; sp = 15
sns.lineplot(x =  np.array(range(fs*st,fs*sp))/1e6*fs, y = data_ch[range(fs*st,fs*sp)], ax = axes[0] , linewidth=0.5 )
sns.lineplot(x =  np.array(range(fs*st,fs*sp))/1e6*fs, y = data_ch_hat[range(fs*st,fs*sp)] , ax = axes[1], linewidth=0.5 )

data_ch = data[:,ch]
data_ch_hat = data_butter[:,ch]
  
fig,axes = plt.subplots(1,2,figsize=(8,4), dpi = 300)
sns.lineplot(x =  np.array(range(fs*st,fs*sp))/1e6*fs, y = data_ch[range(fs*st,fs*sp)], ax = axes[0] , linewidth=0.5 )
sns.lineplot(x =  np.array(range(fs*st,fs*sp))/1e6*fs, y = data_ch_hat[range(fs*st,fs*sp)] , ax = axes[1], linewidth=0.5 )
###########
###########
###########
###########
fig,axes = plt.subplots(2,2,figsize=(8,8), dpi = 300)
sns.histplot(adj_xcorr_025[np.triu_indices( len(adj_xcorr_025), k = 1)], ax = axes[0][0])
sns.histplot(adj_pear[np.triu_indices( len(adj_pear), k = 1)], ax = axes[0][1])
sns.histplot(adj_spear[np.triu_indices( len(adj_spear), k = 1)], ax = axes[1][0])


fig,axes = plt.subplots(2,2,figsize=(8,8), dpi = 300)
sns.histplot(adj_butter_xcorr[np.triu_indices( len(adj_butter_xcorr), k = 1)], ax = axes[0][0])
sns.histplot(adj_butter_pear[np.triu_indices( len(adj_butter_pear), k = 1)], ax = axes[0][1])
sns.histplot(adj_butter_spear[np.triu_indices( len(adj_butter_spear), k = 1)], ax = axes[1][0])
###########
###########
###########
###########
n1=18; n2 = 37
d1= data_hat[:,n1]
d2= data_hat[:,n2]
print(f"\nx_xorr:   {np.round( adj_xcorr_025[n1,n2],2 )}"  ) 
print(f"Pearson:  {np.round( pearsonr(d1, d2)[0],2 )}; p-value: {np.round( pearsonr(d1, d2)[1],2 )}"  ) 
print(f"Spearman: {np.round( spearmanr(d1, d2)[0],2 )}; p-value: {np.round( spearmanr(d1, d2)[1],2 )}"  ) 

adj_xcorr_025[n1,n2]; adj_pear[n1,n2]; adj_spear[n1,n2]

fig,axes = plt.subplots(1,1,figsize=(8,4), dpi = 300)
sns.regplot(  x = data_hat[range(fs*st, fs*sp),  n1], y= data_hat[range(fs*st, fs*sp),n2], ax = axes , scatter_kws={"s":0.05})



d1= data_hat[:,n1]
d2= data_hat[:,n2]
print(f"\nx_xorr:   {np.round( adj_butter_xcorr[n1,n2],2 )}"  ) 
print(f"\nPearson:  {np.round( pearsonr(d1, d2)[0],2 )}; p-value: {np.round( pearsonr(d1, d2)[1],2 )}"  ) 
print(f"Spearman: {np.round( spearmanr(d1, d2)[0],2 )}; p-value: {np.round( spearmanr(d1, d2)[1],2 )}"  ) 


fig,axes = plt.subplots(1,1,figsize=(8,4), dpi = 300)
sns.regplot(  x = data_butter[range(fs*st, fs*sp),  n1], y= data_butter[range(fs*st, fs*sp),n2], ax = axes , scatter_kws={"s":0.1})






elecLoc["Tissue_segmentation_distance_from_label_2"]   
elecLoc["electrode_name"]   
    
    
eeg.columns    
    

    
tmp = np.intersect1d(elecLoc["electrode_name"]   , eeg.columns  , return_indices = True )    
    
    
elecLoc["Tissue_segmentation_distance_from_label_2"]   
tmp2 = np.array(elecLoc.iloc[tmp[1],:]["Tissue_segmentation_distance_from_label_2"]    )
    
adjjj = adj_xcorr
adjjj = adj_pear
adjjj = adj_spear
adjjj = adj_MI
ind_wm = np.where(tmp2 > 0)[0]
ind_gm = np.where(tmp2 <= 0)[0]

tmp_wm = adjjj[ind_wm[:,None], ind_wm[None,:]]
tmp_gm = adjjj[ind_gm[:,None], ind_gm[None,:]]

np.mean(tmp_gm)
np.mean(tmp_wm)

order = np.argsort(tmp2)
tmp2[order][63]
adj_xcorr_ord = adj_xcorr[order[:,None], order[None,:]]
adj_pear_ord = adj_pear[order[:,None], order[None,:]]
adj_spear_ord = adj_spear[order[:,None], order[None,:]]
adj_MI_ord = adj_MI[order[:,None], order[None,:]]
"""