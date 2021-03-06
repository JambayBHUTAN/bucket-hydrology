#! /usr/bin/env python

# Started by A. Wickert
# 25 July 2019
# Updated by J. Jones
# Starting 08 Oct 2019

import numpy as np
from matplotlib import pyplot as plt
import sys

class reservoir(object):
    """
    Generic reservoir. Accepts new water (recharge), and sends it to other
    reservoirs and/or out of the system (discharge) at a rate that is 
    proportional to the amount of water held in the reservoir.
    """

    import numpy as np

    def __init__(self, t_efold, f_to_discharge=1., Hmax=np.inf):
        """
        t_efold: e-folding time for reservoir depletion (same units as time 
                 steps; typically days)
        f_to_discharge: fraction of the water lost during that e-folding time
                        that exfiltrates to river discharge (as opposed to 
                        entering one or more other reservoirs)
        Hmax: Maximum water volume that can be held
        """
        self.Hwater = 0.
        self.Hmax = Hmax
        self.t_efold = t_efold
        self.excess = 0.
        self.Hout = np.nan
        self.f_to_discharge = f_to_discharge
    
    def recharge(self, H):
        """
        Recharge can be positive (precipitation) or negative
        (evapotranspiration)
        """
        excess = 0.
        if self.Hwater < 0:
            # Allowing ET in top layer only.
            self.Hwater = 0
        elif self.Hwater+H <= self.Hmax:
            self.Hwater += H
        elif self.Hwater+H > self.Hmax:
            excess = self.Hwater+H - self.Hmax
            self.Hwater = self.Hmax
        self.excess += excess

    def discharge(self, dt):
        dH = self.Hwater * (1 - np.exp(-dt/self.t_efold))
        self.H_exfiltrated = self.excess + dH * self.f_to_discharge
        self.H_infiltrated = dH * (1 - self.f_to_discharge)
        self.Hwater -= dH
        self.excess = 0.

class buckets(object):
    """
    Incorportates a list of reservoirs into a linear hierarchy that sends water 
    either downwards our out to the surface.
    
    reservoir_list: list of subsurface layers in order from top to bottom
                    (surface to deep groundwater)
    dt: time step (typically in days)
    
    """

    def __init__(self, reservoir_list, dt=1):
        self.reservoirs = reservoir_list
        self.dt = dt
        self.rain = None
        self.ET = None
        # Evapotranspiration
        self.Chang_I = 41.47044637
        self.Chang_a_i = 6.75E-7*self.Chang_I**3 \
                         - 7.72E-5*self.Chang_I**2 \
                         + 1.7912E-2*self.Chang_I \
                         + 0.49239
    
    def set_rainfall_time_series(self, rain):
        self.rain = np.array(rain)
    
    def export_Hlist(self):
        """
        Export the list of water depths, for reinitialization
        (e.g., to start after a spin-up phase or to restart a paused model run)
        """
        Hlist = []
        for reservoir in self.reservoirs:
            Hlist.append( reservoir.Hwater )
        return Hlist
    
    def initialize(self, Hlist=None):
        """
        Part of CSDMS BMI
        Can use this to initialize from an old run or a spin-up
        """
        if Hlist is not None:
            i = 0
            for reservoir in self.reservoirs:
                reservoir.Hwater = Hlist[i]
                i += 1
    
    def update(self, rain_at_timestep, ET_at_timestep=0.):
        """
        Updates water flow for one time step (typically a day)
        
        NOTE FALLACY: recharging before discharging,
        even though during the same time step
        consider changing to use half-recharge from each time step
        """
        # Top layer is special: interacts with atmosphere
        recharge_at_timestep = rain_at_timestep - ET_at_timestep
        self.reservoirs[0].recharge(recharge_at_timestep)
        self.reservoirs[0].discharge(self.dt)
        Qi = self.reservoirs[0].H_exfiltrated
        for i in range(1, len(self.reservoirs)):
            self.reservoirs[i].recharge(self.reservoirs[i-1].H_infiltrated)
            self.reservoirs[i].discharge(self.dt)
            Qi += self.reservoirs[i].H_exfiltrated
        return Qi
    
    def evapotranspirationChang2019(self, Tmax, Tmin, photoperiod):
        """
        Modified daily Thorntwaite Equation
        """
        
        Teff = 0.5 * 0.69 * (3*Tmax - Tmin)
        C = photoperiod/360.

        # Simple and inefficient logical implementation
        # Is this ET or PET?
        # I will add/subtract from the top reservoir only.
        self.ET = C*(-415.85 + 32.24*Teff - 0.43*Teff**2) * (Teff >= 26) \
                   + 16.*C * (10.*Teff / self.Chang_I)**self.Chang_a_i \
                     * (Teff > 0) * (Teff < 26)

    def set_evapotranspiration(self, ET):
        """
        User provides ET time series
        """
        self.ET = np.array(ET)

    def run(self, rain=None, ET=False):
        self.Q = [] # discharge
        if rain is not None:
            if self.rain is not None:
                print "Warning: overwriting existing rainfall time series."
            self.set_rainfall_time_series(rain)
        if self.rain is None:
            sys.exit("Please set the rainfall time series")
        self.time = np.arange(len(self.rain)) * self.dt
        if ET:
            for ti in range(len(self.rain)):
                Qi = self.update(rain[ti], self.ET[ti])
                self.Q.append(Qi)
        else:
            print "Warning: neglecting evapotranspiration."
            for ti in range(len(self.rain)):
                Qi = self.update(rain[ti])
                self.Q.append(Qi)
        self.Q = np.array(self.Q)

    def plot(self, Qdata=None):
        """
        Plot rainfall and discharge.
        Optionally pass specific discharge data to plot this as well.
        """
        fig = plt.figure()
        plt.xlabel('Time [days]', fontsize=14)
        plt.ylabel('[mm/day]', fontsize=14)
        plt.bar(self.time, height=self.rain/self.dt, width=1., align='center', label='Rainfall', linewidth=0, alpha=0.5)
        #plt.plot(self.time, self.rain/self.dt, 'b-', label='Rainfall', alpha=0.5)
        plt.twinx()
        if Qdata is not None:
            plt.plot(self.time, Qdata/self.dt, 'b',
                    label='Unit discharge data', linewidth=2)
        plt.plot(self.time, self.Q/self.dt, 'k',
                label='Unit discharge model', linewidth=2)
        plt.ylim(0, plt.ylim()[-1])
        plt.legend(fontsize=11)
        plt.ylabel('[mm/day]', fontsize=14)
        plt.tight_layout()
        plt.show()

    def computeNashSutcliffeEfficiency(self, Qdata):
        """
        Compute the NSE of the model outputs vs. a set of supplied data
        """
        _realvalue = np.isfinite(self.Q * Qdata)
        NSE_num = np.sum( (self.Q[_realvalue] - Qdata[_realvalue])**2 )
        NSE_denom = np.sum((Qdata[_realvalue] - np.mean(Qdata[_realvalue]))**2)
        if np.sum(1 - _realvalue):
            print "Calculated with ", np.sum(1 - _realvalue), "no-data points"
        self.NSE = 1 - NSE_num / NSE_denom
        
