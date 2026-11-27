%% SOLAR_RANKINE_R134A  Interactive solar-driven R-134a (Freon) Rankine cycle model
%  Two modes:  1 = steady-state design point (hours of sun, sun angle, pump power -> W_out)
%              2 = 24 h transient simulation: collector -> storage tank -> Rankine cycle,
%                  with equipment switches, energy-balance checks and plots.
%  Mode 2 uses the same equations, controller and defaults as the Python/Streamlit app.
%
%  Sunlight heats a direct-evaporation collector (the evaporator). R-134a vapor
%  expands through a turbine, condenses, and a pump returns the liquid to the
%  evaporator. A thermal store can carry surplus daytime heat into the night.
%
%  USAGE:   >> solar_rankine_R134a
%           Answer each prompt, or press Enter to accept the [default].
%           No toolboxes needed (base MATLAB, R2016b or newer).
%
%  OUTPUT (mode 1): W_out (net turbine work minus pump work) in W, state-point table,
%           daily energy in Wh, a T-s diagram, and an optional sweep of
%           evaporator temperature.
%
% Assumptions:
%   - Steady flow, no pressure drops in evaporator, condenser or piping.
%   - State 1: saturated liquid leaving the condenser.
%   - State 3: saturated vapor leaving the evaporator (no superheat).
%   - Turbine and pump use constant isentropic efficiencies.
%   - Pump input power sets the mass flow rate. If the collector cannot supply
%     enough heat to boil that flow, the flow is reduced to what the sun can boil.
%   - Collector faces the sun's azimuth. Incidence cosine = sin(elevation + tilt).
%   - Collector heat output per area = eta0*G*cos(theta) - a1*dT - a2*dT^2,
%     with dT = T_evap - T_ambient (standard quadratic collector model).
%   - Sun angle and irradiance are held constant over the exposure window.
%   - Storage is assumed to deliver heat at the evaporator temperature.
%   - Properties: R-134a saturation table (NIST-quality equation of state,
%     ASHRAE reference state: h = s = 0 for saturated liquid at -40 C),
%     interpolated with PCHIP. Units: kJ, kg, kPa, K.

clear; clc; close all;
tab = loadR134aTable();

fprintf('\n=== Solar R-134a Rankine cycle ===\n');
fprintf('Press Enter to accept the [default] shown for any input.\n\n');
mode = askNum('Mode: 1 = steady-state design point, 2 = 24 h transient simulation', 1, 1, 2);
if round(mode) == 2
    runTransient(tab);
    return;
end

%% ---------------- Inputs ----------------
tsun  = askNum('Hours of direct sun per day [h]', 6, 0.1, 24);
alpha = askNum('Sun elevation above horizon [deg]', 60, 0, 90);
beta  = askNum('Collector tilt from horizontal, facing the sun [deg]', 30, 0, 90);
A     = askNum('Collector (evaporator) aperture area [m^2]', 6, 0.1, 1e4);
DNI   = askNum('Direct beam irradiance [W/m^2]', 900, 0, 1100);
Tamb  = askNum('Ambient temperature [C]', 25, -20, 50);
Te    = askNum('Evaporator saturation temperature [C]', 80, 20, 95);
Tcd   = askNum('Condenser saturation temperature, daytime [C]', 30, 0, Te-10);
Tcn   = askNum('Condenser saturation temperature, night [C]', 20, 0, Te-10);
Wp    = askNum('Pump input power [W]', 30, 0.1, 1e5);
eta_t = askNum('Turbine isentropic efficiency [-]', 0.80, 0.3, 1);
eta_p = askNum('Pump isentropic efficiency [-]', 0.70, 0.2, 1);
eta_s = askNum('Thermal storage efficiency [-] (0 = no storage)', 0.8, 0, 1);

eta0 = 0.75;  a1 = 1.5;  a2 = 0.005;     % evacuated-tube style collector
if askYN('Edit collector coefficients (eta0, a1, a2)?', false)
    eta0 = askNum('  Optical efficiency eta0 [-]', eta0, 0.2, 0.95);
    a1   = askNum('  Loss coefficient a1 [W/m^2/K]', a1, 0, 10);
    a2   = askNum('  Loss coefficient a2 [W/m^2/K^2]', a2, 0, 0.1);
end
doPlot  = askYN('Show T-s diagram?', true);
doSweep = askYN('Sweep evaporator temperature to find the best value?', true);

%% ---------------- Solar input ----------------
cosTh = max(0, sind(alpha + beta));            % cosine of incidence angle
Geff  = DNI * cosTh;                           % beam irradiance on the aperture [W/m^2]
dT    = Te - Tamb;
qcol  = max(0, eta0*Geff - a1*dT - a2*dT^2);   % useful heat per area [W/m^2]
Qsol  = A * qcol;                              % useful heat from collector [W]
if Geff > 0, eta_c = qcol/Geff; else, eta_c = 0; end

%% ---------------- Daytime cycle ----------------
d = rankineCycle(Te, Tcd, eta_t, eta_p, tab);
mdot_pump = (Wp/1000)*eta_p / (d.v1*(d.Pe - d.Pc));   % kg/s the pump can move
mdot_sol  = Qsol/1000 / d.qin;                        % kg/s the sun can boil
mdot      = min(mdot_pump, mdot_sol);
Qreq      = mdot_pump * d.qin * 1000;                 % heat needed at full pump flow [W]
surplus   = max(0, Qsol - Qreq);                      % collector heat not used [W]

W_turb = mdot * d.wt   * 1000;                        % [W]
W_pump = mdot * d.wp   * 1000;                        % [W]
W_out  = W_turb - W_pump;                             % [W]
Q_in   = mdot * d.qin  * 1000;                        % [W]
Q_out  = mdot * (d.h4 - d.h1) * 1000;                 % heat rejected [W]
eta_carnot = 1 - (Tcd+273.15)/(Te+273.15);
if Geff > 0, eta_sys = W_out/(Geff*A); else, eta_sys = 0; end

%% ---------------- Night operation from storage ----------------
Wn_out = 0;  tn = 0;  Es = 0;  dn = [];  mdot_n = 0;
if eta_s > 0 && surplus > 0
    dn      = rankineCycle(Te, Tcn, eta_t, eta_p, tab);
    mdot_n  = (Wp/1000)*eta_p / (dn.v1*(dn.Pe - dn.Pc));
    Qn      = mdot_n * dn.qin * 1000;                 % heat draw at night [W]
    Es      = eta_s * surplus * tsun;                 % stored heat available [Wh]
    tn      = min(24 - tsun, Es/Qn);                  % night run time [h]
    Wn_out  = mdot_n * dn.wnet * 1000;                % [W]
end
E_day   = W_out  * tsun;                              % [Wh]
E_night = Wn_out * tn;                                % [Wh]
E_tot   = E_day + E_night;
if Geff*A*tsun > 0, eta_daily = E_tot/(Geff*A*tsun); else, eta_daily = 0; end

%% ---------------- Report ----------------
fprintf('\n================ RESULTS ================\n');
fprintf('SOLAR INPUT\n');
fprintf('  Incidence angle            : %6.1f deg (cos = %.3f)\n', acosd(min(cosTh,1)), cosTh);
fprintf('  Beam on aperture           : %6.1f W/m^2\n', Geff);
fprintf('  Collector efficiency       : %6.1f %%\n', 100*eta_c);
fprintf('  Useful collector heat      : %6.0f W\n', Qsol);

fprintf('\nCYCLE STATE POINTS (daytime, condenser at %.1f C)\n', Tcd);
fprintf('  State   T [C]    P [kPa]   h [kJ/kg]\n');
fprintf('    1    %6.1f   %8.1f   %8.2f   saturated liquid, condenser exit\n', Tcd, d.Pc, d.h1);
fprintf('    2     ~%5.1f   %8.1f   %8.2f   compressed liquid, pump exit\n', Tcd, d.Pe, d.h2);
fprintf('    3    %6.1f   %8.1f   %8.2f   saturated vapor, turbine inlet\n', Te, d.Pe, d.h3);
if d.x4 <= 1
    fprintf('    4    %6.1f   %8.1f   %8.2f   turbine exit, quality x = %.3f\n', Tcd, d.Pc, d.h4, d.x4);
else
    fprintf('    4       n/a   %8.1f   %8.2f   turbine exit, superheated vapor\n', d.Pc, d.h4);
end

fprintf('\nPER KILOGRAM OF R-134a\n');
fprintf('  Turbine work   w_t   : %7.2f kJ/kg\n', d.wt);
fprintf('  Pump work      w_p   : %7.2f kJ/kg\n', d.wp);
fprintf('  Heat added     q_in  : %7.2f kJ/kg\n', d.qin);
fprintf('  Thermal efficiency   : %7.2f %%   (Carnot limit %.2f %%, ratio %.2f)\n', ...
        100*d.eta, 100*eta_carnot, d.eta/eta_carnot);

fprintf('\nPOWER, DAYTIME\n');
if mdot_pump <= mdot_sol
    fprintf('  Mass flow            : %7.4f kg/s (set by pump power; sun has %.0f W spare)\n', mdot, surplus);
else
    fprintf('  Mass flow            : %7.4f kg/s (limited by sunlight; pump could move %.4f)\n', mdot, mdot_pump);
end
fprintf('  Heat in (solar)      : %7.1f W\n', Q_in);
fprintf('  Turbine power        : %7.1f W\n', W_turb);
fprintf('  Pump power used      : %7.1f W\n', W_pump);
fprintf('  Heat rejected        : %7.1f W\n', Q_out);
fprintf('  >>> W_out (net)      : %7.1f W\n', W_out);
fprintf('  Solar-to-work eff.   : %7.2f %%\n', 100*eta_sys);

fprintf('\nDAY/NIGHT ENERGY\n');
if tn > 0
    fprintf('  Stored heat          : %7.0f Wh (surplus %.0f W x %.1f h x store eff. %.2f)\n', Es, surplus, tsun, eta_s);
    fprintf('  Night run time       : %7.2f h at %.1f W net (condenser %.1f C, x4 = %.3f)\n', tn, Wn_out, Tcn, dn.x4);
    if tn >= 24 - tsun
        fprintf('  (Storage can run the plant all night; some stored heat is left over.)\n');
    end
elseif surplus > 0
    fprintf('  Storage off: %.0f W of collector heat is not used (defocus or vent).\n', surplus);
else
    fprintf('  No surplus heat, so the plant stops when the sun goes down.\n');
end
fprintf('  Energy, daytime      : %7.0f Wh\n', E_day);
fprintf('  Energy, night        : %7.0f Wh\n', E_night);
fprintf('  Energy, total/day    : %7.0f Wh   (24 h average %.1f W)\n', E_tot, E_tot/24);
fprintf('  Daily solar-to-work  : %7.2f %%\n', 100*eta_daily);

if d.x4 < 0.88
    fprintf('\nWARNING: turbine exit quality %.2f is below about 0.88. Expect blade erosion.\n', d.x4);
end
if W_out <= 0
    fprintf('\nWARNING: no net work at these conditions (check sun angle, area, temperatures).\n');
end

%% ---------------- T-s diagram ----------------
if doPlot
    figure('Name','T-s diagram','Color','w');
    plot([tab.sf; flipud(tab.sg)], [tab.T; flipud(tab.T)], 'k-', 'LineWidth', 1); hold on;
    [S1, T1] = cyclePath(tab, d, Te, Tcd, eta_p);
    plot(S1, T1, 'b-o', 'LineWidth', 1.8, 'MarkerFaceColor', 'b');
    names = {'1','2','3','4'};
    idx   = [1 2 numel(S1)-2 numel(S1)-1];
    for k = 1:4
        text(S1(idx(k)) + 0.01, T1(idx(k)) + 2, names{k}, 'FontWeight', 'bold');
    end
    leg = {'Saturation dome', 'Daytime cycle'};
    if tn > 0
        [S2, T2] = cyclePath(tab, dn, Te, Tcn, eta_p);
        plot(S2, T2, 'r--s', 'LineWidth', 1.4);
        leg{end+1} = 'Night cycle (from storage)';
    end
    xlabel('Entropy s [kJ/kg-K]'); ylabel('Temperature [C]');
    title('R-134a Rankine cycle on a T-s diagram'); grid on;
    legend(leg, 'Location', 'southwest');
    xlim([0.15 1.0]);
end

%% ---------------- Evaporator temperature sweep ----------------
if doSweep
    Tsw = (Tcd + 20) : 2.5 : 95;
    if isempty(Tsw)
        fprintf('\nSweep skipped: condenser temperature too close to the 95 C limit.\n');
    else
        Wsw = zeros(size(Tsw));  eth = Wsw;  ecl = Wsw;
        for k = 1:numel(Tsw)
            dk  = rankineCycle(Tsw(k), Tcd, eta_t, eta_p, tab);
            dTk = Tsw(k) - Tamb;
            qk  = max(0, eta0*Geff - a1*dTk - a2*dTk^2);       % W/m^2
            Wsw(k) = qk/1000/dk.qin * dk.wnet * 1000;           % net W per m^2, flow set by sun
            eth(k) = dk.eta;
            if Geff > 0, ecl(k) = qk/Geff; end
        end
        [Wbest, kb] = max(Wsw);
        fprintf('\nSWEEP (flow set by sunlight, per m^2 of collector)\n');
        fprintf('  Best evaporator temperature: %.1f C -> %.1f W/m^2 net (thermal eff. %.2f %%)\n', ...
                Tsw(kb), Wbest, 100*eth(kb));
        figure('Name','Evaporator temperature sweep','Color','w');
        subplot(2,1,1);
        plot(Tsw, Wsw, 'b-o', 'LineWidth', 1.5); hold on;
        plot(Tsw(kb), Wbest, 'rp', 'MarkerSize', 12, 'MarkerFaceColor', 'r');
        ylabel('Net work [W/m^2 collector]'); grid on;
        title('Effect of evaporator temperature');
        subplot(2,1,2);
        plot(Tsw, 100*eth, 'b-o', Tsw, 100*ecl, 'g-s', 'LineWidth', 1.5);
        xlabel('Evaporator temperature [C]'); ylabel('Efficiency [%]'); grid on;
        legend('Cycle thermal efficiency', 'Collector efficiency', 'Location', 'best');
    end
end

%% ======================= Local functions =======================
function c = rankineCycle(Te, Tc, eta_t, eta_p, tab, valveOpen)
% Ideal-pressure Rankine cycle, states numbered as in Borgnakke & Sonntag:
% 1 = pump inlet, 2 = pump exit, 3 = turbine inlet, 4 = turbine exit.
    if nargin < 6, valveOpen = true; end                 % false = turbine isolated, throttle bypass
    c.Pe = sat(tab, 'P', Te);   c.Pc = sat(tab, 'P', Tc);
    c.h1 = sat(tab, 'hf', Tc);  c.v1 = sat(tab, 'vf', Tc);
    c.wp = c.v1*(c.Pe - c.Pc)/eta_p;                     % kPa*m^3/kg = kJ/kg
    c.h2 = c.h1 + c.wp;
    c.h3 = sat(tab, 'hg', Te);  s3 = sat(tab, 'sg', Te);
    sfc = sat(tab, 'sf', Tc);   sgc = sat(tab, 'sg', Tc);
    hgc = sat(tab, 'hg', Tc);
    c.x4s = (s3 - sfc)/(sgc - sfc);                      % isentropic exit quality
    h4s   = c.h1 + c.x4s*(hgc - c.h1);
    if valveOpen
        c.wt = eta_t*(c.h3 - h4s);
    else
        c.wt = 0;                                        % isenthalpic throttle, h4 = h3
    end
    c.h4  = c.h3 - c.wt;
    c.x4  = (c.h4 - c.h1)/(hgc - c.h1);                  % > 1 means superheated exit
    c.qin  = c.h3 - c.h2;
    c.wnet = c.wt - c.wp;
    c.eta  = c.wnet/c.qin;
end

function [S, T] = cyclePath(tab, c, Te, Tc, eta_p)
% Points (s, T) that trace the cycle on a T-s diagram. Liquid heating is drawn
% along the saturated-liquid line, which is a close approximation.
    s1 = sat(tab, 'sf', Tc);
    s2 = s1 + c.wp*(1 - eta_p)/(Tc + 273.15);            % pump entropy generation
    Tl = linspace(Tc, Te, 25);
    Sl = sat(tab, 'sf', Tl);
    s3 = sat(tab, 'sg', Te);
    sgc = sat(tab, 'sg', Tc);
    if c.x4 <= 1
        s4 = s1 + c.x4*(sgc - s1);   T4 = Tc;
    else
        hgc = sat(tab, 'hg', Tc);
        T4  = Tc + (c.h4 - hgc)/0.9;                     % cp of vapor ~0.9 kJ/kg-K
        s4  = sgc + 0.9*log((T4 + 273.15)/(Tc + 273.15));
    end
    S = [s1, s2, Sl(2:end), s3, s4, s1];
    T = [Tc, Tc, Tl(2:end), Te, T4, Tc];
end

function y = sat(tab, name, T)
% Saturation property of R-134a at temperature T [C] by PCHIP interpolation.
    if strcmp(name, 'P')
        y = exp(ppval(tab.pp.P, T));
    else
        y = ppval(tab.pp.(name), T);
    end
end

function val = askNum(label, def, lo, hi)
    def = min(max(def, lo), hi);
    while true
        s = strtrim(input(sprintf('%s [%g]: ', label, def), 's'));
        if isempty(s), val = def; return; end
        val = str2double(s);
        if ~isnan(val) && isfinite(val) && val >= lo && val <= hi, return; end
        fprintf('  Enter a number between %g and %g.\n', lo, hi);
    end
end

function tf = askYN(label, defYes)
    if defYes, tag = 'Y/n'; else, tag = 'y/N'; end
    s = lower(strtrim(input(sprintf('%s (%s): ', label, tag), 's')));
    if isempty(s), tf = defYes; else, tf = (s(1) == 'y'); end
end

function tab = loadR134aTable()
% Columns: T [C], P [kPa], vf [m^3/kg], hf, hg [kJ/kg], sf, sg [kJ/kg-K]
    D = [
    0  292.8032  0.0007723338  51.85594  250.4594  0.2043895  0.9314753;
    2.5  320.2635  0.0007773199  55.2232  251.9112  0.2165834  0.9301261;
    5  349.6586  0.0007824298  58.6081  253.3482  0.2287249  0.9288513;
    7.5  381.0767  0.00078767  62.01122  254.7695  0.2408167  0.9276448;
    10  414.6075  0.000793048  65.43319  256.1741  0.2528617  0.9265007;
    12.5  450.3422  0.0007985715  68.87469  257.5609  0.2648627  0.9254131;
    15  488.3739  0.0008042491  72.33642  258.929  0.2768225  0.9243761;
    17.5  528.7968  0.0008100901  75.81915  260.2772  0.288744  0.9233838;
    20  571.7069  0.0008161044  79.32369  261.6043  0.3006305  0.9224302;
    22.5  617.2019  0.0008223032  82.8509  262.909  0.3124849  0.9215094;
    25  665.3809  0.0008286984  86.40173  264.1899  0.3243107  0.9206151;
    27.5  716.3449  0.0008353033  89.97718  265.4456  0.3361111  0.9197413;
    30  770.1963  0.0008421323  93.57835  266.6745  0.3478899  0.9188815;
    32.5  827.0396  0.0008492016  97.2064  267.8748  0.3596506  0.9180291;
    35  886.981  0.0008565287  100.8626  269.0446  0.3713974  0.9171771;
    37.5  950.1287  0.0008641335  104.5484  270.1819  0.3831345  0.9163183;
    40  1016.593  0.0008720378  108.2652  271.2845  0.3948662  0.9154451;
    42.5  1086.487  0.0008802662  112.0148  272.3498  0.4065975  0.9145494;
    45  1159.924  0.0008888461  115.7989  273.3751  0.4183336  0.9136225;
    47.5  1237.024  0.0008978087  119.6196  274.3573  0.4300801  0.912655;
    50  1317.905  0.0009071892  123.4791  275.2929  0.4418431  0.9116368;
    52.5  1402.693  0.0009170279  127.38  276.1783  0.4536296  0.9105567;
    55  1491.514  0.0009273708  131.325  277.0089  0.4654469  0.9094023;
    57.5  1584.499  0.0009382715  135.3173  277.7799  0.4773036  0.9081598;
    60  1681.784  0.0009497919  139.3606  278.4856  0.4892092  0.9068137;
    62.5  1783.51  0.0009620054  143.4591  279.1194  0.5011746  0.9053463;
    65  1889.822  0.0009749988  147.6176  279.6736  0.5132122  0.9037372;
    67.5  2000.874  0.0009888766  151.8417  280.1393  0.5253368  0.9019626;
    70  2116.826  0.001003766  156.1384  280.5057  0.5375658  0.8999944;
    72.5  2237.848  0.001019824  160.5157  280.76  0.5499201  0.8977989;
    75  2364.12  0.00103725  164.9837  280.8861  0.5624257  0.895335;
    77.5  2495.836  0.001056297  169.5552  280.8644  0.5751147  0.8925514;
    80  2633.203  0.001077302  174.2462  280.6695  0.5880287  0.8893831;
    82.5  2776.451  0.00110072  179.0782  280.2684  0.6012227  0.8857445;
    85  2925.833  0.001127188  184.0804  279.6161  0.6147719  0.8815196;
    87.5  3081.633  0.001157647  189.2945  278.649  0.6287845  0.8765439;
    90  3244.183  0.001193565  194.7841  277.2715  0.643425  0.8705692;
    92.5  3413.88  0.001237445  200.654  275.3273  0.658967  0.8631877;
    95  3591.232  0.001294156  207.1023  272.5254  0.6759296  0.8536375;
    97.5  3776.96  0.001375708  214.6007  268.1867  0.6955565  0.8401297;
    100  3972.379  0.001535678  225.1539  259.5392  0.7231658  0.8153145;
    ];
    tab.T  = D(:,1);  tab.P  = D(:,2);  tab.vf = D(:,3);
    tab.hf = D(:,4);  tab.hg = D(:,5);  tab.sf = D(:,6);  tab.sg = D(:,7);
    % Piecewise-cubic Hermite (PCHIP) coefficients, built once (same result as interp1 'pchip').
    tab.pp.P  = pchip(tab.T, log(tab.P));
    tab.pp.vf = pchip(tab.T, tab.vf);
    tab.pp.hf = pchip(tab.T, tab.hf);  tab.pp.hg = pchip(tab.T, tab.hg);
    tab.pp.sf = pchip(tab.T, tab.sf);  tab.pp.sg = pchip(tab.T, tab.sg);
end

%% ======================= 24 h transient mode =======================
function runTransient(tab)
% Interactive front end for the 24 h simulation. Defaults equal the Python app's
% baseline, so pressing Enter at every prompt reproduces it.
    fprintf('\n--- 24 h transient simulation ---\n');
    fprintf('Sun -> collector -> storage tank -> evaporator -> turbine -> condenser -> pump.\n');
    fprintf('The tank is a transient control volume; the four cycle devices are steady-flow.\n\n');
    P.lat    = askNum('Latitude [deg N]', 34.05, -60, 60);
    P.day    = round(askNum('Day of year (172 = Jun 21, 355 = Dec 21)', 172, 1, 365));
    P.clear  = askNum('Sky clearness [-] (1 = clear sky)', 1, 0.2, 1);
    P.Tmean  = askNum('Mean ambient temperature [C]', 22, 5, 40);
    P.Tswing = askNum('Daily ambient swing, peak to peak [K]', 12, 0, 25);
    P.area   = askNum('Collector area [m^2]', 8, 0.5, 100);
    P.tilt   = askNum('Collector tilt from horizontal [deg]', 30, 0, 90);
    P.tankL  = askNum('Storage tank water volume [L]', 500, 50, 1e4);
    P.pumpW  = askNum('Pump input power at full flow [W]', 30, 1, 1e4);
    P.eta_t  = askNum('Turbine isentropic efficiency [-]', 0.80, 0.3, 1);
    P.eta_p  = askNum('Pump isentropic efficiency [-]', 0.70, 0.2, 1);
    P.Tcut   = askNum('Plant starts when the tank reaches [C]', 70, 30, 95);
    P.Tfull  = askNum('Full flow when the tank reaches [C]', 85, P.Tcut + 1, 98);
    P.pumpOn    = askYN('Pump running?', true);
    P.valveOpen = askYN('Turbine valve open? (n = throttle bypass, no work)', true);
    P.collOn    = askYN('Collector exposed to the sun?', true);
    P.eta0 = 0.75;  P.a1 = 1.5;  P.a2 = 0.005;       % collector
    P.UA = 3;  P.Tinit = 30;                          % tank loss [W/K], start-up temperature [C]
    P.pinch = 5;  P.approach = 8;  P.Tmax = 98;       % K, K, C
    if askYN('Edit collector, tank-loss and cycle details?', false)
        P.eta0     = askNum('  Optical efficiency eta0 [-]', P.eta0, 0.2, 0.95);
        P.a1       = askNum('  Loss coefficient a1 [W/m^2/K]', P.a1, 0, 10);
        P.a2       = askNum('  Loss coefficient a2 [W/m^2/K^2]', P.a2, 0, 0.1);
        P.UA       = askNum('  Tank heat-loss coefficient UA [W/K]', P.UA, 0, 50);
        P.pinch    = askNum('  Tank to turbine-inlet temperature drop [K]', P.pinch, 1, 20);
        P.approach = askNum('  Condenser above ambient [K]', P.approach, 3, 20);
        P.Tmax     = askNum('  Collector defocuses near [C]', P.Tmax, 80, 99);
    end
    fprintf('\nIntegrating four days (three warm-up days, then the reported day) ...\n');
    R = simulateDay(P, tab);
    reportDay(P, R);
    plotDay(P, R, tab);
end

function R = simulateDay(P, tab)
% Integrate the tank ODE with the quasi-steady cycle. State vector:
%  y(1) tank temperature [C]       y(2) incident beam energy [J]
%  y(3) collector heat [J]         y(4) evaporator heat [J]     y(5) tank loss [J]
%  y(6) turbine work [J]           y(7) pump work [J]           y(8) condenser heat [J]
%  y(9) exergy fed to the cycle [J]  y(10) circulated mass [kg]
% The energy terms are integrated by the same solver as the tank temperature,
% so the energy balance can be checked without post-processing error.
    C     = P.tankL * 4186;                    % tank heat capacity [J/K], 1 kg/L, cp = 4.186 kJ/kg-K
    nWarm = 3;                                 % warm-up days so the tank state is periodic
    t0    = nWarm*86400;  tEnd = (nWarm + 1)*86400;
    tEval = 0:300:tEnd;                        % 5 min output grid
    y0    = [P.Tinit, zeros(1, 9)];
    opts  = odeset('RelTol', 1e-6, 'AbsTol', [1e-8, 1e-3*ones(1,8), 1e-9], 'MaxStep', 300);
    [t, Y] = ode45(@(tt, y) plantRHS(tt, y, P, tab, C), tEval, y0, opts);
    i0 = find(t >= t0, 1, 'first');
    t  = t(i0:end);  Y = Y(i0:end, :);
    n  = numel(t);
    S  = plantInstant(P, t(1), Y(1,1), tab);
    S  = repmat(S, 1, n);
    for i = 2:n
        S(i) = plantInstant(P, t(i), Y(i,1), tab);
    end
    R.th = (t - t0)/3600;                      % hours of the reported day
    R.S  = S;
    R.Ts = Y(:,1);
    wh = 1/3600;  D = Y(end,:) - Y(1,:);
    K.Einc = D(2)*wh;  K.Ecol = D(3)*wh;  K.Eev = D(4)*wh;  K.Eloss = D(5)*wh;
    K.Wt = D(6)*wh;    K.Wp = D(7)*wh;    K.Qc = D(8)*wh;   Ex = D(9)*wh;  K.mass = D(10);
    K.Wnet = K.Wt - K.Wp;
    K.eta_cycle = safeDiv(K.Wnet, K.Eev);
    K.eta_daily = safeDiv(K.Wnet, K.Einc);
    K.eta_II    = safeDiv(K.Wnet, Ex);
    dd = diff(R.th(:)');
    w  = [dd(1)/2, (dd(1:end-1) + dd(2:end))/2, dd(end)/2];     % trapezoid weights, sum = 24 h
    frac = [S.frac];  running = frac > 0.05;  night = [S.alt] <= 0;
    K.runH = sum(w(running));  K.nightRunH = sum(w(running & night));
    K.peakW = max([S.Wnet]);  K.TsMax = max(R.Ts);  K.TsMin = min(R.Ts);
    x4 = [S.x4];  K.x4min = min(x4(running));  if isempty(K.x4min), K.x4min = NaN; end
    K.PeMax = max([S.Pe]);
    % conservation checks
    dU = C*(R.Ts(end) - R.Ts(1));                                % J
    K.resTank  = dU - (D(3) - D(4) - D(5));                     % tank: dU - (Qcol - Qev - Qloss)
    K.resTankRel = abs(K.resTank)/max(D(3), 1);
    K.resCyc   = D(4) - D(8) - (D(6) - D(7));                   % cycle: Qev - Qcond - Wnet
    K.resCycRel = abs(K.resCyc)/max(D(4), 1);
    R.K = K;  R.P = P;
end

function dy = plantRHS(t, y, P, tab, C)
    d  = plantInstant(P, t, y(1), tab);
    dy = [(d.Qcol - d.Qev - d.Qloss)/C; d.Geff*P.area; d.Qcol; d.Qev; d.Qloss; ...
          d.Wt; d.Wp; d.Qc; d.Ex; d.mdot];
end

function d = plantInstant(P, t, Ts, tab)
% Every instantaneous quantity for time t [s] and tank temperature Ts [C].
    hour = mod(t/3600, 24);
    [sinAlt, alt] = sunPos(hour, P.lat, P.day);
    dni  = beamIrr(sinAlt, P.day, P.clear);
    Geff = dni * cosInc(hour, P.lat, P.day, P.tilt);
    Ta   = P.Tmean + 0.5*P.Tswing*cos(2*pi*(hour - 15)/24);
    taper = clip01((P.Tmax - Ts)/5);                  % collector defocuses near Tmax
    if P.collOn
        dT   = Ts - Ta;
        Qcol = P.area*max(0, P.eta0*Geff - P.a1*dT - P.a2*dT^2)*taper;
    else
        Qcol = 0;
    end
    Qloss = P.UA*(Ts - Ta);
    Te = min(Ts - P.pinch, 95);                       % turbine-inlet (evaporator) temperature
    Tc = max(Ta + P.approach, 1);                     % condensing temperature (table starts at 0 C)
    if P.pumpOn
        frac = clip01((Ts - P.Tcut)/max(P.Tfull - P.Tcut, 1e-6));
    else
        frac = 0;
    end
    frac = frac*clip01((Te - Tc - 6)/4);              % no flow without enough temperature lift
    d = struct('hour',hour,'alt',alt,'dni',dni,'Geff',Geff,'Ta',Ta,'Ts',Ts,'Te',Te,'Tc',Tc, ...
               'Qcol',Qcol,'Qloss',Qloss,'frac',frac,'mdot',0,'Qev',0,'Qc',0,'Wt',0,'Wp',0, ...
               'Wnet',0,'Ex',0,'Pe',NaN,'Pc',NaN,'x4',NaN,'eta',0);
    if frac > 0
        c = rankineCycle(Te, Tc, P.eta_t, P.eta_p, tab, P.valveOpen);
        m = frac*P.pumpW/1000/c.wp;                   % kg/s: pump power sets the flow
        d.mdot = m;
        d.Qev  = m*c.qin*1000;
        d.Qc   = m*(c.h4 - c.h1)*1000;
        d.Wt   = m*c.wt*1000;
        d.Wp   = m*c.wp*1000;
        d.Wnet = d.Wt - d.Wp;
        d.Pe   = c.Pe;  d.Pc = c.Pc;
        d.x4   = min(c.x4, 1);
        d.eta  = c.eta;
        d.Ex   = d.Qev*(1 - (Ta + 273.15)/(Ts + 273.15));
    end
end

function reportDay(P, R)
    K = R.K;
    fprintf('\n================ 24 h RESULTS ================\n');
    fprintf('ENERGY (Wh per day)\n');
    fprintf('  Beam energy on collector : %8.0f\n', K.Einc);
    fprintf('  Collector heat           : %8.0f   (collector efficiency %.1f %%)\n', K.Ecol, 100*safeDiv(K.Ecol, K.Einc));
    fprintf('  Heat to evaporator       : %8.0f\n', K.Eev);
    fprintf('  Tank heat loss           : %8.0f\n', K.Eloss);
    fprintf('  Turbine work             : %8.0f\n', K.Wt);
    fprintf('  Pump work                : %8.0f\n', K.Wp);
    fprintf('  Heat rejected            : %8.0f\n', K.Qc);
    fprintf('  >>> NET WORK W_out       : %8.0f Wh   (24 h average %.1f W)\n', K.Wnet, K.Wnet/24);
    fprintf('\nPERFORMANCE\n');
    fprintf('  Peak net power           : %8.1f W\n', K.peakW);
    fprintf('  Cycle efficiency         : %8.2f %%\n', 100*K.eta_cycle);
    fprintf('  Solar to work            : %8.2f %%\n', 100*K.eta_daily);
    fprintf('  Second-law efficiency    : %8.1f %%\n', 100*K.eta_II);
    fprintf('  Plant run time           : %8.2f h  (%.2f h after sunset)\n', K.runH, K.nightRunH);
    fprintf('  Tank temperature range   : %8.1f to %.1f C\n', K.TsMin, K.TsMax);
    fprintf('  R-134a circulated        : %8.0f kg\n', K.mass);
    fprintf('\nCONSERVATION CHECKS\n');
    fprintf('  Tank:  dU - (Qcol - Qevap - Qloss) = %.2e J  (relative %.1e)\n', K.resTank, K.resTankRel);
    fprintf('  Cycle: Qevap - Qcond - Wnet        = %.2e J  (relative %.1e)\n', K.resCyc, K.resCycRel);
    fprintf('\nFEEDBACK\n');
    if ~P.pumpOn
        fprintf('  [i] Pump switched off: no mass flow and no power.\n');
    elseif K.runH < 0.1
        fprintf('  [x] The plant never started: the tank stayed below %.0f C. Add collector area or reduce tank volume.\n', P.Tcut);
    end
    if ~P.valveOpen && P.pumpOn
        fprintf('  [!] Turbine valve closed: heat goes through the bypass throttle and no work is produced.\n');
    end
    if K.runH >= 0.1 && K.x4min < 0.88
        fprintf('  [!] Turbine exit quality fell to %.2f (below about 0.88 liquid droplets erode the blades).\n', K.x4min);
    end
    if K.TsMax >= P.Tmax - 1
        fprintf('  [!] The tank reached the collector limit and the collector defocused: heat was thrown away.\n');
    end
    if K.nightRunH > 0.5
        fprintf('  [ok] The plant ran %.1f h after sunset on stored heat.\n', K.nightRunH);
    end
    if K.resTankRel < 1e-4 && K.resCycRel < 1e-6
        fprintf('  [ok] Energy balances close.\n');
    else
        fprintf('  [x] Energy balance does not close; tighten the solver tolerance.\n');
    end
end

function plotDay(P, R, tab)
    S = R.S;  th = R.th;  blue = [0.145 0.49 0.88];  orange = [0.957 0.447 0.188];
    figure('Name', '24 h simulation', 'Color', 'w', 'Position', [60 60 1150 750]);
    subplot(2,3,1);
    plot(th, R.Ts, '-', 'Color', blue, 'LineWidth', 1.8); hold on;
    plot(th, [S.Ta], '-', 'Color', orange, 'LineWidth', 1.8);
    ylabel('Temperature [C]'); xlabel('Solar time [h]'); grid on; xlim([0 24]);
    legend('Tank', 'Ambient', 'Location', 'best'); title('Temperatures');
    subplot(2,3,2);
    plot(th, [S.Qcol]/1000, '-', 'Color', orange, 'LineWidth', 1.8); hold on;
    plot(th, [S.Qev]/1000,  '-', 'Color', blue,   'LineWidth', 1.8);
    ylabel('Heat rate [kW]'); xlabel('Solar time [h]'); grid on; xlim([0 24]);
    legend('Collector', 'To evaporator', 'Location', 'best'); title('Heat flows');
    subplot(2,3,3);
    plot(th, [S.Wnet], '-', 'Color', blue, 'LineWidth', 1.8);
    ylabel('Net power [W]'); xlabel('Solar time [h]'); grid on; xlim([0 24]); title('Net power output');
    subplot(2,3,4);
    plot(th, [S.mdot]*1000, '-', 'Color', blue, 'LineWidth', 1.8);
    ylabel('Mass flow [g/s]'); xlabel('Solar time [h]'); grid on; xlim([0 24]); title('R-134a flow');
    subplot(2,3,5);
    yyaxis left;  plot(th, [S.Pe], '-', 'Color', blue, 'LineWidth', 1.8); ylabel('Evaporator pressure [kPa]');
    yyaxis right; plot(th, [S.Pc], '-', 'Color', orange, 'LineWidth', 1.8); ylabel('Condenser pressure [kPa]');
    xlabel('Solar time [h]'); grid on; xlim([0 24]); title('Cycle pressures');
    subplot(2,3,6);
    [~, kp] = max([S.Wnet]);
    if S(kp).frac > 0
        c = rankineCycle(S(kp).Te, S(kp).Tc, P.eta_t, P.eta_p, tab, P.valveOpen);
        plot([tab.sf; flipud(tab.sg)], [tab.T; flipud(tab.T)], 'k-', 'LineWidth', 1); hold on;
        [S1, T1] = cyclePath(tab, c, S(kp).Te, S(kp).Tc, P.eta_p);
        plot(S1, T1, '-o', 'Color', blue, 'LineWidth', 1.8, 'MarkerFaceColor', blue);
        xlabel('Entropy s [kJ/kg-K]'); ylabel('Temperature [C]'); xlim([0.15 1.0]); grid on;
        title(sprintf('T-s at peak power (%.1f h)', th(kp)));
    else
        axis off; text(0.1, 0.5, 'Plant never ran: no cycle to draw');
    end
end

function [sinAlt, alt] = sunPos(hour, lat, n)
    [phi, dec] = hemi(lat, 23.45*sind(360*(284 + n)/365));
    w = 15*(hour - 12);
    sinAlt = sind(phi)*sind(dec) + cosd(phi)*cosd(dec)*cosd(w);
    sinAlt = max(-1, min(1, sinAlt));
    alt = asind(sinAlt);
end

function c = cosInc(hour, lat, n, tilt)
% Equator-facing tilted surface: cos(theta) = sin(dec) sin(phi-tilt) + cos(dec) cos(phi-tilt) cos(w)
    [phi, dec] = hemi(lat, 23.45*sind(360*(284 + n)/365));
    w = 15*(hour - 12);
    c = max(0, sind(dec)*sind(phi - tilt) + cosd(dec)*cosd(phi - tilt)*cosd(w));
end

function [phi, dec] = hemi(lat, dec)
% Mirror the southern hemisphere so the collector always faces the equator.
    if lat < 0
        phi = -lat;  dec = -dec;
    else
        phi = lat;
    end
end

function g = beamIrr(sinAlt, n, clearness)
% Meinel clear-sky direct normal irradiance, blended to zero between 0 and 3 deg altitude.
    if sinAlt <= 0
        g = 0;  return;
    end
    airMass = 1/max(sinAlt, 0.02);
    e0 = 1 + 0.033*cosd(360*n/365);
    g  = 1353*e0*0.7^(airMass^0.678);
    g  = clearness*g*min(1, sinAlt/sind(3));
end

function y = clip01(x)
    y = min(max(x, 0), 1);
end

function r = safeDiv(a, b)
    if b > 0, r = a/b; else, r = 0; end
end
