respnw = """start
title "RESP {name}"
set driver:linopt 0
set int:cando_txs f
set int:cando_nw f

memory total {memory} mb noverify


geometry nocenter
{geometry}
{zcoord}
end

charge {charge}

xtb
 acc 0.1
end

driver
 maxiter 100
end

task xtb optimize ignore

basis "ao basis" spherical
 * library {aobasis}
end

basis "cd basis" spherical bse
 * library {cdbasis}
end


dft
  noio
  {disp}
  xc {xcfun}
  grid {grid} nodisk
  mult {mult}
  maxiter {nscf}
  convergence lshift {lshift} energy 1d-7
  noprint "final vectors analysis"
end

driver
 maxiter {nopt}
end

task dft optimize ignore

unset "dft:cd*"
unset "basis:cd*"

basis "ao basis" spherical
 * library 6-31g*
end

dft
 xc hfexch 1.0
 vectors input atomic
end

task dft

esp
 {constraint}
 restrain hfree
end

task esp
"""


fit = """#!/usr/bin/env python3
import numpy as np
import copy

# Parameters
natoms = {natoms}
names  = {names}
nconf  = {nconf}
files  = {files}
ncons  = {ncons}
charge = {charge}

# Constrain hydrogens to have same charge
hncons = 0
hcons = []
for i,name in enumerate(names):
    if name in ["HA2","HB2","HG2","HD2","HE2","HZ2","HG12","HD22"]: 
        for j,jname in enumerate(names):
            if jname[:-1]==name[:-1] and jname[-1] != name[-1]:
                hncons += 1
                hcons.append([i,j])

# Constrain NME, ACE, and amide bond charges (for AMBER99)
cons = [
{cons}
]

grids = []
geometries = np.zeros((nconf,natoms,3))
npoints = np.zeros(nconf, dtype=int)
A = np.zeros((natoms+ncons+hncons+1,natoms+ncons+hncons+1))
B = np.zeros(natoms+ncons+hncons+1)

for i,file in enumerate(files):
    filename = file + ".xyz"
    with open(filename,"r") as fh:
        fh.readline(); fh.readline()
        for atom in range(natoms):
            line = fh.readline().split()
            geometries[i,atom] = [float(x)/0.529177 for x in line[1:4]]
    filename = file + ".grid"
    with open(filename,"r") as fh:
        npoints[i] = int(fh.readline().split()[0])
        grids.append(np.zeros((npoints[i],4)))
        for point in range(npoints[i]):
            line = fh.readline().split()
            grids[i][point] = [float(x) for x in line]

for iconf in range(nconf):
    for k in range(npoints[iconf]):
        for iatom in range(natoms):
            disti = np.linalg.norm(geometries[iconf,iatom] - grids[iconf][k,:3])
            B[iatom] += grids[iconf][k,3]/disti
            for jatom in range(iatom,natoms):
                distj = np.linalg.norm(geometries[iconf,jatom] - grids[iconf][k,:3])
                A[iatom,jatom] += 1.0/(disti*distj)

# Symmetrize matrix
for iatom in range(natoms):
    for jatom in range(iatom,natoms):
        A[jatom,iatom] = copy.copy(A[iatom,jatom])

# Total charge constraint
A[:natoms,natoms] = 1.0
A[natoms,:natoms] = 1.0

# NME, ACE, and amide bond constraints
for icons in range(ncons):
    A[cons[icons][0]-1,natoms+icons+1] = 1.0
    A[natoms+icons+1,cons[icons][0]-1] = 1.0
    B[natoms+icons+1] = cons[icons][1]

# Hydrogen bond constraints
for icons in range(hncons):
    A[hcons[icons][0],natoms+ncons+icons+1] = 1.0
    A[hcons[icons][1],natoms+ncons+icons+1] = -1.0
    A[natoms+ncons+icons+1,hcons[icons][0]] = 1.0
    A[natoms+ncons+icons+1,hcons[icons][1]] = -1.0

# Start from solution without restraints
qold = np.linalg.inv(A) @ B

# Hyperbolic restraints are non-linear. Do 50 iterations at most
for iter in range(50):
    Acur = copy.deepcopy(A)

    # Add restraint contribution to matrix
    for i in range(natoms):
        
        # Hydrogens are free of restraints
        if names[i][0] == "H": continue

        # Skip charges already constrained
        skip = False
        for j in range(ncons):
            if i == cons[j][0]-1: 
                skip = True
                break
        if skip: continue
        Acur[i,i] += 0.005 * qold[i]/np.sqrt(qold[i]**2 + 0.01)

    # Solve linear equation system
    q = np.linalg.inv(Acur) @ B

    # Check convergence
    delta = np.amax(np.abs(q-qold))
    print("iter {{}}, delta: {{}}".format(iter,delta))
    if delta < 0.000001: break

    # Copy current solution to qold
    qold = copy.deepcopy(q)

# Print charges to STDOUT
print("")
print(" RESP charges")
{printing}
print("")
"""

slurm_header = """#!/bin/bash
#SBATCH --account={account}
#SBATCH --time={time}
#SBATCH --nodes={nodes}
#SBATCH --ntasks-per-node={ntasks}
#SBATCH --job-name={jname}
#SBATCH --error={jname}-%j.err
#SBATCH --output={jname}-%j.out
#SBATCH --partition={partition}

cleanup()
{{
cp *.xyz $SLURM_SUBMIT_DIR || :
cp *.log $SLURM_SUBMIT_DIR || :
cp *.txt $SLURM_SUBMIT_DIR || :
cp *.json $SLURM_SUBMIT_DIR || :
}}

trap cleanup SIGINT SIGTERM SIGKILL SIGSEGV SIGCONT
source /etc/profile.d/modules.sh
module purge
module load python
module load gcc/9.3.0
module load openmpi

export NWCHEM_BASIS_LIBRARY="/cluster/apps/nwchem/nwchem-7.0.2/src/basis/libraries.bse/"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NWC_RANKS_PER_DEVICE=0
export ARMCI_OPENIB_DEVICE=mlx5_0
export OMPI_MCA_opal_warn_on_missing_libcuda=0
export https_proxy="http://proxy.emsl.pnl.gov:3128"
export http_proxy="http://proxy.emsl.pnl.gov:3128"
export NWBIN=/big_scratch/nwchems_`id -u`.img
export NWCHEM_IMAGE="ghcr.io/edoapra/nwchem-singularity/nwchem-720.ompi41x:latest"

srun -N $SLURM_NNODES -n $SLURM_NNODES apptainer pull -F --name $NWBIN oras://$NWCHEM_IMAGE
export APPTAINERENV_SCRATCH_DIR={scratch}
export APPTAINERENV_OMP_NUM_THREADS=1
export APPTAINERENV_NWCHEM_BASIS_LIBRARY=$NWCHEM_BASIS_LIBRARY


cd {scratch}
"""

shotmdp = """integrator     = md
dt              = 0.001
nsteps          = 0             ; Maximum number of (minimization) steps to perform
nstxout         = 0
nstfout         = 1             ; Forces (important)
nstenergy       = 1             ; Write energies to disk every nstenergy steps
nstxtcout       = 0             ; Write coordinates to disk every nstxtcout steps
xtc_grps        = System               ; Which coordinate group(s) to write to disk
energygrps      = System               ; Which energy group(s) to write to disk
constraints     = none
nstlist         = 1
rlist           = 333.3
vdwtype         = cut-off
coulombtype     = cut-off
rcoulomb        = 333.3
rvdw            = 333.3
pbc             = xyz
"""

slurm_tdrive = """
# Create a Virtual Environment
if [ -d "venv" ]; then
  echo "Virtual environment already exists"
else
  python -m venv venv
fi
source venv/bin/activate

# Set proxy server
export https_proxy=http://proxy.emsl.pnl.gov:3128
export http_proxy=http://proxy.emsl.pnl.gov:3128

python -m pip install --upgrade pip
git clone git@code.emsl.pnl.gov:cheung_group/ptmpsi.git
cd ptmpsi
python -m pip install .
cd ..

export NWCHEM_COMMAND="srun --mpi=pmi2 -N $SLURM_NNODES -n $SLURM_NPROCS apptainer exec --bind {scratch},$NWCHEM_BASIS_LIBRARY $NWBIN nwchem"
"""

slurm_torsiondrive = """
cp ${{SLURM_SUBMIT_DIR}}/dihedrals.txt .
cp ${{SLURM_SUBMIT_DIR}}/extras.txt .
cp ${{SLURM_SUBMIT_DIR}}/nwchem.nw .

torsiondrive-launch torsiondrive.nw dihedrals.txt -c extras.txt -g 15 -e nwchem --native_opt -v

nlines=$(( $(head -1 scan.txt) + 2 ))
split -d -a2 -l$nlines --additional-suffix=.xyz scan.xyz scan-

for file in `ls scan-*.xyz`; do
name=${{file%.xyz}}.nw
cat <<EOF >$name 
start
memory {memory} mb
set int:cando_txs f
set int:cando_nw f

geometry
load "$file"
end

charge {charge}

basis "ao basis" spherical
 * library def2-tzvp
end
basis "cd basis" spherical bse
 * library def2-universal-jfit
end

dft
  mult {mult}
  grid nodisk fine
  xc r2scan
  disp vdw 4
end

task dft gradient
EOF

$NWCHEM_COMMAND $name > ${{name%.nw}}.log

done

cleanup
"""

slurm_resp = """
cp ${SLURM_SUBMIT_DIR}/alpha.nw .
cp ${SLURM_SUBMIT_DIR}/beta.nw .
cp ${SLURM_SUBMIT_DIR}/fit.py .

echo "Running alpha-helix conformer"
srun --mpi=pmi2 -N $SLURM_NNODES -n $SLURM_NPROCS apptainer exec --bind /big_scratch $NWBIN nwchem alpha.nw > alpha.log

echo "Running beta-strand conformer"
srun --mpi=pmi2 -N $SLURM_NNODES -n $SLURM_NPROCS apptainer exec --bind /big_scratch $NWBIN nwchem beta.nw > beta.log

# Create a Virtual Environment
if [ -d "venv" ]; then
  echo "Virtual environment already exists"
else
  python -m venv venv
fi
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install numpy

echo "\\n Starting RESP fitting"
python fit.py

cp alpha.log $SLURM_SUBMIT_DIR
cp beta.log $SLURM_SUBMIT_DIR
"""

slurm_hess = """
cp ${SLURM_SUBMIT_DIR}/alpha_hess.nw .
cp ${SLURM_SUBMIT_DIR}/beta_hess.nw .

echo "\\n Running alpha-helix hessian"
srun --mpi=pmi2 -N $SLURM_NNODES -n $SLURM_NPROCS apptainer exec --bind /big_scratch $NWBIN nwchem alpha_hess.nw > alpha_hess.log

echo "\\n Running beta-sheet hessian"
srun --mpi=pmi2 -N $SLURM_NNODES -n $SLURM_NPROCS apptainer exec --bind /big_scratch $NWBIN nwchem beta_hess.nw > beta_hess.log

cp alpha_hess.log $SLURM_SUBMIT_DIR
cp beta_hess.log $SLURM_SUBMIT_DIR
"""


hessnw = """start
memory total {memory} mb noverify
title "{name} hessian calculation"

set int:cando_txs f
set int:cando_nw f


geometry nocenter
{geometry}
{zcoord}
end

basis "ao basis" spherical
 * library {aobasis}
end

basis "cd basis" spherical
 * library {cdbasis}
end

charge {charge}

dft
 noio
 {disp}
 mult {mult}
 xc {xcfun}
 grid {grid} nodisk
 maxiter {nscf}
 convergence energy 1d-7
 noprint "final vectors analysis"
end

freq
 fd_delta {delta}
end

task dft frequencies
"""

torsnw = """start
memory total {memory} mb
title "{name} torsion scan"

set int:cando_txs f
set int:cando_nw f
set driver:linopt 0

geometry
{geometry}
 zcoord
 end
end

basis "ao basis" spherical
 * library {aobasis}
end

basis "cd basis" spherical bse
 * library {cdbasis}
end

charge {charge}

dft
 noio
 grid {grid} nodisk
 mult {mult}
 {disp}
 xc {xcfun}
 maxiter {nscf}
 convergence lshift {lshift} energy 1d-7
 noprint "final vectors analysis"
end

task dft optimize ignore
"""

slurm_tdrive_run = """
nlines=$(( $( cat {tail}.xyz | wc -l)-2 ))
geom=`cat {tail}.xyz | tail -$nlines`
geom="${{geom//$'\\n'/\\\\n}}"
sed -i "s/@geometry@/$geom/" {tail}_tdrive.nw

torsiondrive-launch {tail}_tdrive.nw dihedrals{idx}.txt -c extras{idx}.txt -g {spacing} -e nwchem --native_opt -v

mv scan.xyz scan-{tail}.xyz
mv qdata.txt qdata-{tail}.txt

rm -rf opt_tmp

"""

forcebalance_input = """$options
jobtype newton
forcefield ffbonded.itp ffnonbonded.itp posre.itp
trust0 0.1
penalty_type L1
search_tolerance 1e-2
duplicate_pnames 1
lm_guess 100.0
penalty_additive 1.0
priors
  PDIHMULS1B : 100.0
  PDIHMULS2B : 100.0
  PDIHMULS3B : 100.0
  PDIHMULS4B : 100.0
  PDIHMULS5B : 100.0
  PDIHMULS6B : 100.0
/priors
$end

$target
type         torsionprofile_gmx
name         {name1}
coords       {name1}_all.g96
attenuate
energy_denom 1.5
energy_upper 10.0
writelevel   2
energy_mode  qm_minimum
$end

$target
type         torsionprofile_gmx
name         {name2}
coords       {name2}_all.g96
attenuate
energy_denom 1.5
energy_upper 10.0
writelevel   2
energy_mode  qm_minimum
$end
"""

installptmpsi = """
if [ -d "venv" ]; then
  echo "Virtual environment already exists"
else
  python -m venv _venv
fi
source _venv/bin/activate

python -m pip install --upgrade pip
git clone git@code.emsl.pnl.gov:cheung_group/ptmpsi.git
cd ptmpsi
python -m pip install .
cd ..
"""

nwconstraint = "constrain  {: 10.6f}  {:5d}\n "
pyconstraint = "[{},{}],\n"
coordinates = "{}   {: 14.8f}   {: 14.8f}   {: 14.8f}\n"
pyprint = """print("{name}: {{:10.6f}}".format(q[{atom}]))\n"""
runsingularity = "srun --mpi=pmi2 -N $SLURM_NNODES -n $SLURM_NPROCS apptainer exec --bind {scratch},$NWCHEM_BASIS_LIBRARY $NWBIN nwchem {name}.nw > {name}.log\n\n"
slurm_copy = "cp ${{SLURM_SUBMIT_DIR}}/{filename} . \n"
