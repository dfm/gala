# coding: utf-8
# cython: boundscheck=False
# cython: nonecheck=False
# cython: cdivision=True
# cython: wraparound=False
# cython: profile=False

from __future__ import division, print_function

__author__ = "adrn <adrn@astro.columbia.edu>"

# Third-party
import numpy as np
cimport numpy as np
np.import_array()
import cython
cimport cython

# Project
from .core import Potential, CartesianCompositePotential

cdef extern from "math.h":
    double sqrt(double x) nogil
    double fabs(double x) nogil

class CPotential(Potential):
    """
    A baseclass for representing gravitational potentials. You must specify
    a function that evaluates the potential value (func). You may also
    optionally add a function that computes derivatives (gradient), and a
    function to compute second derivatives (the Hessian) of the potential.

    Parameters
    ----------
    func : function
        A function that computes the value of the potential.
    gradient : function (optional)
        A function that computes the first derivatives (gradient) of the potential.
    hessian : function (optional)
        A function that computes the second derivatives (Hessian) of the potential.
    parameters : dict (optional)
        Any extra parameters that the functions (func, gradient, hessian)
        require. All functions must take the same parameters.

    """

    def __init__(self, c_class, parameters=dict()):
        # store C instance
        self.c_instance = c_class(**parameters)

        # HACK?
        super(CPotential, self).__init__(func=lambda x: x, parameters=parameters)

        # self.value = getattr(self.c_instance, 'value')
        # self.gradient = getattr(self.c_instance, 'gradient', None)
        # self.hessian = getattr(self.c_instance, 'hessian', None)

    def value(self, q):
        """
        Compute the value of the potential at the given position(s).

        Parameters
        ----------
        q : array_like, numeric
            Position to compute the value of the potential.
        """
        tmp = np.zeros(len(q))
        self.c_instance.value(np.array(q), tmp)
        return tmp

    def gradient(self, q):
        """
        Compute the gradient of the potential at the given position(s).

        Parameters
        ----------
        q : array_like, numeric
            Position to compute the gradient.
        """
        try:
            return self.c_instance.gradient(np.array(q))
        except AttributeError,TypeError:
            raise ValueError("Potential C instance has no defined "
                             "gradient function")

    def hessian(self, q):
        """
        Compute the Hessian of the potential at the given position(s).

        Parameters
        ----------
        q : array_like, numeric
            Position to compute the Hessian.
        """
        try:
            return self.c_instance.hessian(np.array(q))
        except AttributeError,TypeError:
            raise ValueError("Potential C instance has no defined "
                             "Hessian function")

    # ----------------------------
    # Functions of the derivatives
    # ----------------------------
    def acceleration(self, q):
        """
        Compute the acceleration due to the potential at the given position(s).

        Parameters
        ----------
        q : array_like, numeric
            Position to compute the acceleration.
        """
        try:
            return -self.c_instance.gradient(np.array(q))
        except AttributeError,TypeError:
            raise ValueError("Potential C instance has no defined "
                             "gradient function")

    def mass_enclosed(self, q):
        """
        Estimate the mass enclosed within the given position by assuming the potential
        is spherical. This is not so good!

        Parameters
        ----------
        q : array_like, numeric
            Position to compute the mass enclosed.
        """
        try:
            return self.c_instance.mass_enclosed(np.array(q))
        except AttributeError,TypeError:
            raise ValueError("Potential C instance has no defined "
                             "mass_enclosed function")

# ==============================================================================

cdef class _CPotential:

    cpdef value(self, double[:,::1] q, double[::1] pot):
        cdef int nparticles, ndim, k
        nparticles = q.shape[0]
        ndim = q.shape[1]

        for k in range(nparticles):
            pot[k] = self._value(q,k)

    cdef public double _value(self, double[:,::1] q, int k) nogil:
        return 0.

    # -------------------------------------------------------------
    cpdef gradient(self, double[:,::1] q):
        cdef int nparticles, ndim, k
        nparticles = q.shape[0]
        ndim = q.shape[1]

        cdef double [:,::1] grad = np.zeros((nparticles,ndim))
        for k in range(nparticles):
            self._gradient(q, grad, k)

        return np.array(grad)

    cdef public void _gradient(self, double[:,::1] r, double[:,::1] grad, int k) nogil:
        grad[0] = 0.
        grad[1] = 0.
        grad[2] = 0.

    # -------------------------------------------------------------
    cpdef hessian(self, double[:,::1] w):
        cdef int nparticles, ndim, k
        nparticles = w.shape[0]
        ndim = w.shape[1]

        cdef double [:,:,::1] hess = np.zeros((nparticles,ndim,ndim))
        for k in range(nparticles):
            self._hessian(w, hess, k)

        return np.array(hess)

    cdef public void _hessian(self, double[:,::1] w, double[:,:,::1] hess, int k) nogil:
        cdef int i,j
        for i in range(3):
            for j in range(3):
                hess[i,j] = 0.

    # -------------------------------------------------------------
    cpdef mass_enclosed(self, double[:,::1] q):
        cdef int nparticles, k
        nparticles = q.shape[0]

        cdef double [:,::1] epsilon = np.zeros((1,3))
        cdef double [::1] mass = np.zeros((nparticles,))
        for k in range(nparticles):
            mass[k] = self._mass_enclosed(q, epsilon, self.G, k)
        return np.array(mass)

    cdef public double _mass_enclosed(self, double[:,::1] q, double [:,::1] epsilon, double Gee, int k) nogil:
        cdef double h, r, dPhi_dr

        # Fractional step-size
        h = 0.01

        # Step-size for estimating radial gradient of the potential
        r = sqrt(q[k,0]*q[k,0] + q[k,1]*q[k,1] + q[k,2]*q[k,2])

        for j in range(3):
            epsilon[0,j] = h * q[k,j]/r + q[k,j]
        dPhi_dr = self._value(epsilon,0)

        for j in range(3):
            epsilon[0,j] = h * q[k,j]/r - q[k,j]
        dPhi_dr -= self._value(epsilon,0)

        return fabs(r*r * dPhi_dr / Gee / (2.*h))
        # return fabs(r*r * dPhi_dr / (2.*h))

# ==============================================================================

class CCompositePotential(CPotential):
    """

    TODO!

    A baseclass for representing gravitational potentials. You must specify
    a function that evaluates the potential value (func). You may also
    optionally add a function that computes derivatives (gradient), and a
    function to compute second derivatives (the Hessian) of the potential.

    Parameters
    ----------
    TODO
    """

    def __init__(self, **kwargs):
        # hurm?
        self.c_instance = _CCompositePotential([p.c_instance for p in kwargs.values()])
        super(CPotential, self).__init__(func=lambda x: x, parameters=dict())

from python cimport PyObject
cdef class _CCompositePotential(_CPotential):

    cdef public list py_instances
    cdef public int ninstances
    cdef PyObject *obj_list[100]
    cdef public double G

    def __init__(self, instance_list):
        """ Need a list of instances of _CPotential classes """
        self.py_instances = list(instance_list)
        self.ninstances = len(instance_list)
        self._more_init()

    cpdef _more_init(self):
        for i in range(self.ninstances):
            self.obj_list[i] = <PyObject *>self.py_instances[i]

    cdef public double _value(self, double[:,::1] q, int k) nogil:
        # whoa this is some whack cython wizardry right here
        #   (stolen from stackoverflow)
        cdef double v = 0.
        for i in range(self.ninstances):
            v += (<_CPotential>(self.obj_list[i]))._value(q, k)
        return v

    cdef public void _gradient(self, double[:,::1] r, double[:,::1] grad, int k) nogil:
        # whoa this is some whack cython wizardry right here
        #   (stolen from stackoverflow)
        cdef double v = 0.

        for i in range(self.ninstances):
            (<_CPotential>(self.obj_list[i]))._gradient(r, grad, k)

    cdef public void _hessian(self, double[:,::1] w, double[:,:,::1] hess, int k) nogil:
        # whoa this is some whack cython wizardry right here
        #   (stolen from stackoverflow)
        for i in range(self.ninstances):
            (<_CPotential>(self.obj_list[i]))._hessian(w, hess, k)

    cdef public double _mass_enclosed(self, double[:,::1] q, double [:,::1] epsilon, double Gee, int k) nogil:
        cdef double mm = 0.
        for i in range(self.ninstances):
            mm += (<_CPotential>(self.obj_list[i]))._mass_enclosed(q, epsilon, Gee, k)
        return mm
