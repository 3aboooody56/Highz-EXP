import skrf as rf
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import os
from os.path import join as pjoin, basename as pbase

def load_s1p(s1p_files, labels=None) -> dict:
    """
    Load S1P files and return a dictionary of label: rf.Network objects.

    Parameters:
    - s1p_files (list of str): Paths to .s1p files.
    - labels (list of str, optional): Labels for the files.

    Returns:
    - dict: {label: rf.Network}
    """
    if labels is None:
        labels = [pbase(f) for f in s1p_files]

    return {label: rf.Network(file) for file, label in zip(s1p_files, labels)}

def LNA_total_reflection(rho_cable_ntwk, rho_LNA_ntwk):
    """Return the total reflection coefficient with multiple reflections between cable and LNA interfaces"""
    rho_cable = rho_cable_ntwk.s[:, 0, 0]
    rho_LNA = rho_LNA_ntwk.s[:, 0, 0]
    a_lna = rho_cable * 1 / (1 - rho_cable*rho_LNA)
    a_lna_ntwk = rf.Network(s=a_lna, f=rho_cable_ntwk.f)
    return a_lna_ntwk

def s11_reflected_power(s11_db, p_in_k=50):
    """Compute reflected power (in Kelvin) given S11 in dB and input power.
    
    Parameters:
    - s11_db: S11 in dB (can be float or NumPy array)
    - p_in_k: Input power in Kelvin (default is 50 K)

    Returns:
    - Reflected power in Kelvin
    """
    R = 10 ** (s11_db / 10)  # power reflection coefficient
    return p_in_k * R

def fit_exp_decay(s1p_ntwk, guess_A_real, guess_A_imag, guess_delay, guess_alpha, save_path=None) -> tuple[complex, float, rf.Network]:
    """Fit the reflection coefficient from an S1P network to a model of the form (A_real + 1j*A_imag) * exp(j*2*pi*f*t_delay).

    Returns
    - A_fitted (complex): Fitted amplitude (complex).
    - t_delay_fitted (float): Fitted time delay.
    - s1p_fitted_ntwk (rf.Network): Fitted reflection coefficient as a Network object.
    """
    f = s1p_ntwk.f
    gamma_meas = s1p_ntwk.s[:, 0, 0]
    gamma_meas_comb = np.concatenate([gamma_meas.real, gamma_meas.imag])

    def reflection_model(freq, A_real, A_imag, t_delay, alpha):
        A = A_real + 1j * A_imag
        decay = np.exp(-alpha * freq)
        model = decay * A * np.exp(1j * 2 * np.pi * freq * t_delay)
        return np.concatenate([model.real, model.imag])

    popt, pcov = curve_fit(
        reflection_model, f, gamma_meas_comb, p0=[guess_A_real, guess_A_imag, guess_delay, guess_alpha]
    )
    A_fitted = popt[0] + 1j * popt[1]
    t_delay_fitted = popt[2]
    alpha_fitted = popt[3]
    s1p_fitted = A_fitted * np.exp(-alpha_fitted * f) * np.exp(1j * 2 * np.pi * f * t_delay_fitted)
    # Create a new Network object with the same frequency and fitted S-parameters
    s1p_fitted_ntwk = rf.Network(s=s1p_fitted, f=f)
    if save_path is not None:
        s1p_fitted_ntwk.write_touchstone(save_path, overwrite=True)
    return A_fitted, t_delay_fitted, alpha_fitted, s1p_fitted_ntwk

def fit_reflection_coeff(s1p_ntwk, guess_A_real, guess_A_imag, guess_delay, save_path=None) -> tuple[complex, float, rf.Network]:
    """Fit the reflection coefficient from an S1P network to a model of the form (A_real + 1j*A_imag) * exp(j*2*pi*f*t_delay).

    Returns
    - A_fitted (complex): Fitted amplitude (complex).
    - t_delay_fitted (float): Fitted time delay.
    - s1p_fitted_ntwk (rf.Network): Fitted reflection coefficient as a Network object.
    """
    f = s1p_ntwk.f
    gamma_meas = s1p_ntwk.s[:, 0, 0]
    gamma_meas_comb = np.concatenate([gamma_meas.real, gamma_meas.imag])

    def reflection_model(freq, A_real, A_imag, t_delay):
        A = A_real + 1j * A_imag
        model = A * np.exp(1j * 2 * np.pi * freq * t_delay)
        return np.concatenate([model.real, model.imag])

    popt, pcov = curve_fit(
        reflection_model, f, gamma_meas_comb, p0=[guess_A_real, guess_A_imag, guess_delay]
    )
    A_fitted = popt[0] + 1j * popt[1]
    t_delay_fitted = popt[2]
    s1p_fitted = A_fitted * np.exp(1j * 2 * np.pi * f * t_delay_fitted)
    # Create a new Network object with the same frequency and fitted S-parameters
    s1p_fitted_ntwk = rf.Network(s=s1p_fitted, f=f)
    if save_path is not None:
        s1p_fitted_ntwk.write_touchstone(save_path, overwrite=True)
    return A_fitted, t_delay_fitted, s1p_fitted_ntwk

def plot_measured_vs_fitted(ntwk_dict, scale='linear', save_plot=True, save_path=None, ylabel='Magnitude', title='Measured vs Fitted Spectrum'):
    """
    Plot magnitude for measured and fitted spectrum data, and a ratio panel (measured/fitted).

    Parameters:
    - ntwk_dict (dict): {'measured': skrf.Network, 'fitted': skrf.Network}
    """
    assert len(ntwk_dict) == 2, "ntwk_dict must contain exactly two items: measured and fitted."
    keys = list(ntwk_dict.keys())
    measured_ntwk = ntwk_dict[keys[0]]
    fitted_ntwk = ntwk_dict[keys[1]]

    freq = measured_ntwk.f
    spec_measured = measured_ntwk.s[:, 0, 0]
    spec_fitted = fitted_ntwk.s[:, 0, 0]

    mag_measured = 20 * np.log10(np.abs(spec_measured)) if scale == 'log' else np.abs(spec_measured)
    mag_fitted = 20 * np.log10(np.abs(spec_fitted)) if scale == 'log' else np.abs(spec_fitted)
    ratio = mag_measured / mag_fitted

    fig, axes = plt.subplots(nrows=2, figsize=(10, 7), sharex=True)
    ax_mag, ax_ratio = axes

    ax_mag.plot(freq / 1e6, mag_measured, label=f'{keys[0]}', color='C0')
    ax_mag.plot(freq / 1e6, mag_fitted, label=f'{keys[1]}', color='C1', linestyle='--')
    ax_mag.set_ylabel(ylabel)
    ax_mag.legend(loc='best')
    ax_mag.grid(True)

    ax_ratio.plot(freq / 1e6, 1 / ratio, color='C2')
    ax_ratio.axhline(1, color='red', linestyle='-', linewidth=1.5, label='measured/fitted =1)')
    ax_ratio.set_ylabel('Fitted/Measured')
    ax_ratio.set_xlabel('Frequency [MHz]')
    ax_ratio.grid(True)
    ax_ratio.legend(loc='best')

    fig.suptitle(title)
    fig.tight_layout(rect=[0, 0, 1, 0.95])

    if save_plot:
        if save_path is not None:
            plt.savefig(save_path)
        else:
            print("! Save path not entered.")

    plt.show()

def plot_s11_reflect(ntwk_dict, scale='linear', save_plot=True, show_phase=True, save_path=None, ylabel='Magnitude', title='S11 Reflection Coefficient'):
    """
    Plot S11 magnitude (and optionally phase) from a dictionary of scikit-rf Network objects.

    Parameters:
    - ntwk_dict (dict): {label: skrf.Network}. Frequency points are in Hz.
    """

    nrows = 2 if show_phase else 1
    fig, axes = plt.subplots(nrows=nrows, figsize=(10, 6), sharex=True)
    if nrows == 1:
        axes = [axes]  # Make it iterable for consistency

    ax_mag = axes[0]
    ax_phase = axes[1] if show_phase else None

    color_cycle = plt.rcParams['axes.prop_cycle'].by_key()['color']

    for idx, (label, ntwk) in enumerate(ntwk_dict.items()):
        freq = ntwk.f  # in Hz
        s11 = ntwk.s[:, 0, 0]

        magnitude = 20 * np.log10(np.abs(s11)) if scale == 'log' else np.abs(s11)
        phase = np.angle(s11, deg=True)

        color = color_cycle[idx % len(color_cycle)]

        ax_mag.plot(freq / 1e6, magnitude, label=f'{label}', color=color)
        if show_phase:
            ax_phase.plot(freq / 1e6, phase, label=f'{label}', color=color, linestyle='--')

    # Format magnitude plot
    ax_mag.set_ylabel(ylabel)
    ax_mag.grid(True)
    ax_mag.legend(loc='best')

    # Format phase plot
    if show_phase:
        ax_phase.set_xlabel('Frequency [MHz]')
        ax_phase.set_ylabel('Phase [deg]')
        ax_phase.grid(True)
        ax_phase.legend(loc='best')

    else:
        ax_mag.set_xlabel('Frequency [MHz]')

    fig.suptitle(title)
    fig.tight_layout(rect=[0, 0, 1, 0.95])

    if save_plot:
        if save_path is not None:
            plt.savefig(save_path)
        else:
            print("! Save path not entered.")

    plt.show()
    
def plot_smith_chart(ntwk_dict, suffix='LNA', save_plot=True, save_dir=None, legend_loc='best', individual=True):
    """
    Plot Smith chart from one or more scikit-rf Network objects.

    Parameters:
    - ntwk_dict (dict): {label: rf.Network} pairs.
    - suffix (str): Used for output filename if saving.
    - save_plot (bool): Whether to save the figure.
    - legend_loc (str): Location of the legend. Default is 'best'.
    - individual (bool): Whether to plot/save individual Smith charts for each network.
    """
    fig, ax = plt.subplots()
    fig.set_size_inches(10, 8)

    for label, ntwk in ntwk_dict.items():
        ntwk.plot_s_smith(ax=ax, label=label, chart_type='z', draw_labels=True, label_axes=True)

    ax.set_title(f'{suffix} Smith Chart')
    ax.legend(loc='center left', bbox_to_anchor=(1.05, 0.5), borderaxespad=0.)
    plt.tight_layout()

    if save_plot:
        suffix = suffix.replace(' ', '_')
        # Save to current directory if no path info is available
        if save_dir is None:
            save_dir = os.getcwd()
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        fig.savefig(pjoin(save_dir, f'{suffix}_smith_chart.png'), bbox_inches='tight')

    plt.show()
    if individual:
        for label, ntwk in ntwk_dict.items():
            fig, ax = plt.subplots()
            fig.set_size_inches(8, 8)
            ntwk.plot_s_smith(ax=ax, label=label, chart_type='z', draw_labels=True, label_axes=True)
            ax.set_title(f'Smith Chart: {label}')
            if save_plot:
                label_safe = label.replace(' ', '_')
                outname = f'{suffix}_smith_{label_safe}.png'
                fig.savefig(outname, bbox_inches='tight')
