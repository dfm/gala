# coding: utf-8

from __future__ import division, print_function

__author__ = "adrn <adrn@astro.columbia.edu>"

# Standard library
import os, sys
import time

# Third-party
import numpy as np
from astropy import log as logger
import astropy.units as u
from scipy.linalg import solve
from scipy.optimize import leastsq

# Project
from ..potential import HarmonicOscillatorPotential, IsochronePotential

__all__ = ['classify_orbit', 'find_box_actions']

def L(w):
    """
    Compute the angular momentum vector of phase-space point(s), `w`

    Parameters
    ----------
    w : array_like
        Array of phase-space positions.
    """
    ndim = w.shape[-1]
    return np.cross(w[...,:ndim//2], w[...,ndim//2:])

def classify_orbit(w):
    """
    Determine whether an orbit is a Box or Loop orbit by figuring out
    whether there is a change of sign of the angular momentum about an
    axis. Returns an array with 3 integers per phase-space point, such
    that:

    - Box = [0,0,0]
    - Short axis Loop = [0,0,1]
    - Long axis Loop = [1,0,0]

    Parameters
    ----------
    w : array_like
        Array of phase-space positions.

    """
    # get angular momenta
    Ls = L(w)

    # if only 2D, add another empty axis
    if w.ndim == 2:
        ntimesteps,ndim = w.shape
        w = w.reshape(ntimesteps*norbits,1,ndim)

    ntimes,norbits,ndim = w.shape

    # initial angular momentum
    L0 = Ls[0]

    # see if at any timestep the sign has changed
    loop = np.ones((norbits,3))
    for ii in range(3):
        ix = np.any(np.sign(L0[...,ii]) != np.sign(Ls[1:,...,ii]), axis=0)
        loop[ix,ii] = 0

    return loop.astype(int)

def flip_coords(w, loop_bit):
    """
    Align circulation with z-axis.

    Parameters
    ----------
    w : array_like
        Array of phase-space positions.
    loop_bit : array_like
        Array of bits that specify axis about which the orbit circulates.
        See docstring for `classify_orbit()`.
    """
    ix = loop_bit[:,0] == 1
    w[:,ix,:3] = w[:,ix,2::-1] # index magic to flip positions
    w[:,ix,3:] = w[:,ix,:2:-1] # index magic to flip velocities
    return w

def generate_n_vectors(N_max, dx=1, dy=1, dz=1):
    """
    TODO:

    """
    vecs = np.meshgrid(np.arange(-N_max, N_max+1, dx),
                       np.arange(-N_max, N_max+1, dy),
                       np.arange(-N_max, N_max+1, dz))
    vecs = np.vstack(map(np.ravel,vecs)).T
    vecs = vecs[np.linalg.norm(vecs,axis=1) <= N_max]
    ix = ((vecs[:,2] > 0) | ((vecs[:,2] == 0) & (vecs[:,1] > 0)) | ((vecs[:,2] == 0) & (vecs[:,1] == 0) & (vecs[:,0] > 0)))
    vecs = vecs[ix]
    return vecs

def unroll_angles(angles, sign=1.):
    """
    Unrolls the angles, `angles`, so they increase continuously instead of
    wrapping at 2π.

    Parameters
    ----------
    angles : array_like
        Array of angles, (ntimes,3).
    sign : numeric (optional)
        TODO:
    """
    n = np.array([0,0,0])
    P = np.zeros_like(angles)
    P[0] = angles[0]

    n = np.cumsum(((angles[1:] - angles[:-1] + 0.5*sign*np.pi)*sign < 0) * 2.*np.pi, axis=0)
    P[1:] = angles[1:] + sign*n
    return P

def check_angle_sampling(nvecs, angles):
    """
    returns a list of the index of elements of n which do not have adequate
    toy angle coverage. The criterion is that we must have at least one sample
    in each Nyquist box when we project the toy angles along the vector n
    """

    checks = np.array([])
    P = np.array([])

    logger.debug("Checking modes:")
    for i,vec in enumerate(nvecs):
        N = np.linalg.norm(vec)
        X = np.dot(angles,vec)

        if(np.abs(np.max(X)-np.min(X)) < 2.*np.pi):
            logger.warning("Need a longer integration window for mode " + str(vec))
            checks = np.append(checks,vec)
            P = np.append(P,(2.*np.pi-np.abs(np.max(X)-np.min(X))))

        elif(np.abs(np.max(X)-np.min(X))/len(X) > np.pi):
            logger.warning("Need a finer sampling for mode " + str(vec))
            checks = np.append(checks,vec)
            P = np.append(P,(2.*np.pi-np.abs(np.max(X)-np.min(X))))

    return checks,P

def action_solver(aa, N_max, dx, dy, dz):
    """
    TODO:

    """

    # unroll the angles so they increase continuously instead of wrap
    angles = unroll_angles(aa[:,3:])

    # generate integer vectors for fourier modes
    nvecs = generate_n_vectors(N_max, dx, dy, dz)

    # make sure we have enough angle coverage
    modes,P = check_angle_sampling(nvecs, angles)

    # TODO: throw out modes?

    n = len(nvecs) + 3
    b = np.zeros(shape=(n, ))
    A = np.zeros(shape=(n,n))

    # top left block matrix: identity matrix summed over timesteps
    A[:3,:3] = len(aa)*np.identity(3)

    actions = aa[:,:3]
    angles = aa[:,3:]

    # top right block matrix: transpose of C_nk matrix (Eq. 12)
    C_T = 2.*nvecs.T * np.sum(np.cos(np.dot(nvecs,angles.T)), axis=-1)
    A[:3,3:] = C_T
    A[3:,:3] = C_T.T

    # lower right block matrix: C_nk dotted with C_nk^T
    CdotC_T = 0.
    for ang in angles:
        v = np.cos(np.dot(nvecs,ang))
        CdotC_T += np.outer(v,v)
    CdotC_T *= 4.*np.dot(nvecs,nvecs.T)
    A[3:,3:] = CdotC_T

    # b vector first three is just sum of toy actions
    b[:3] = np.sum(actions, axis=0)

    # rest of the vector is C dotted with actions
    b[3:] = np.sum(C_T.T.dot(actions.T),axis=1)

    return np.array(solve(A,b)), nvecs

def find_box_actions(t, w, N_max=8):
    """
    Finds actions, angles, and frequencies for a box orbit.
    Takes a series of phase-space points, `w`, from an orbit integration at
    times `t`.

    This code is adapted from Jason Sanders'
    `genfunc <https://github.com/jlsanders/genfunc>`_

    Parameters
    ----------
    t : array_like
        Array of times with shape (ntimes,).
    w : array_like
        Phase-space orbit at times, `t`. Should have shape (ntimes,6).
    N_max : int
        Maximum integer Fourier mode vector length, |n|.
    """

    if w.ndim > 2:
        raise ValueError("w must be a single orbit")

    logger.debug("===== Using triaxial harmonic oscillator toy potential =====")

    t1 = time.time()

    # find best toy potential parameters
    potential = HarmonicOscillatorPotential(omega=[1.,1.,1.])
    def f(omega,w):
        potential.parameters['omega'] = omega
        H = potential.energy(w[...,:3], w[...,3:])
        return np.squeeze(H - np.median(H))

    p,ier = leastsq(f, np.array([10.,10.,10.]), args=(w,))

    if ier < 1 or ier > 4:
        raise ValueError("Failed to fit toy potential to orbit.")

    best_omega = np.abs(p)
    potential = HarmonicOscillatorPotential(omega=best_omega)
    logger.debug("Best omegas ({}) found in {} seconds".format(best_omega,time.time()-t1))

    # Now find toy actions and angles
    action,angle = potential.action_angle(w[...,:3], w[...,3:])
    aa = np.hstack((action,angle))
    if np.any(np.isnan(aa)):
        raise ValueError("NaN value in toy actions or angles!")

    t1 = time.time()
    actions,nvecs = action_solver(aa, N_max, dx=2, dy=2, dz=2)

    logger.debug("Action solution found for N_max={}, size {} symmetric"
                 " matrix in {} seconds"\
                 .format(N_max,len(actions),time.time()-t1))

    print(actions[:3])
    return

    np.savetxt("GF.Sn_box",np.vstack((act[1].T,act[0][3:])).T)

    ang = solver.angle_solver(AA,times,N_matrix,np.ones(3))
    if(ifprint):
        print("Angle solution found for N_max = "+str(N_matrix)+", size "+str(len(ang))+" symmetric matrix in "+str(time.time()-t)+" seconds")

    # Just some checks
    if(len(ang)>len(AA)):
        print("More unknowns than equations")

    return act[0], ang, act[1], AA, omega

def find_actions(t, w, N_max=8):
    """
    Find approximate actions and angles for samples of a phase-space orbit,
    `w`, at times `t`. Uses toy potentials with known, analytic action-angle
    transformations to approximate the true coordinates as a Fourier sum. Uses
    the formalism presented in Sanders & Binney (2014).

    This code is adapted from Jason Sanders'
    `genfunc <https://github.com/jlsanders/genfunc>`_

    Parameters
    ----------
    t : array_like
        Array of times with shape (ntimes,).
    w : array_like
        Phase-space orbits at times, `t`. Should have shape (ntimes,norbits,6).
    N_max : int
        Maximum integer Fourier mode vector length, |n|.
    """

    # first determine orbit
