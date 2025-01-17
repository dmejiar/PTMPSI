import requests
import copy
import numpy as np
import subprocess
from shutil import which
from ..exceptions import FeatureError
from ptmpsi.residues import resdict, Residue
from ptmpsi.math import find_clashes, find_clashes_residue, appendc, prependn
from ptmpsi.protein.mutate import point_mutation, post_translational_modification
from ptmpsi.io import digestpdb, writepdb
from ptmpsi.docking import dock_ligand


class Chain:
    def __init__(self,name):
        self.name = name
        self.nresidues = 0
        self.natoms    = 0
        self.residues  = None



class Protein:
    def __init__(self,filename=None,pdbid=None,uniprotid=None,interactive=False,delwat=True,delhet=True):
        self.filename = filename
        self.pdbid = pdbid
        self.uniprotid = uniprotid
        self.pdbfile = None
        self.chains = None
        self.natoms = 0
        self.nresidues = 0
        self.nonstandard = None
        self.missing     = None
        self.nssbonds = 0
        self.ssbonds = None
        self.charge = None
        
        # Download file from the PDB
        if self.pdbid is not None:
            print("\t Downloading file from the Protein Databank")
            response = requests.get("https://files.rcsb.org/download/"+self.pdbid.upper()+".pdb")
            response.raise_for_status()
            self.pdbfile = response.text.splitlines()
            with open(self.pdbid+".pdb","w") as fh:
                for line in self.pdbfile:
                    fh.write(line+"\n")
            del(response)
            
        # Download file from AlphaFold Database
        elif self.uniprotid is not None:
            print("\t Downloading file from the AlphaFold Protein Structure Database")
            response = requests.get("https://alphafold.ebi.ac.uk/files/AF-"+self.uniprotid.upper()+"-F1-model_v4.pdb")
            response.raise_for_status()
            self.pdbfile = response.text.splitlines()
            with open(self.uniprotid+".pdb","w") as fh:
                for line in self.pdbfile:
                    fh.write(line+"\n")
        
        # Read local file
        elif self.filename is not None:
            print("\t Reading local PDB file")
            with open(self.filename,'r') as fh:
                self.pdbfile = fh.readlines()

        # Process PDB file
        if self.pdbfile is not None:
            digestpdb(self,interactive,delwat,delhet)

        # Initialize a dummy chain
        else:
            self.chains = [Chain("A")]
            self.chains[0].residues = []
            self.chains[0].natoms = 0
            self.chains[0].nresidues = 0

        return


    def write_pdb(self,pdbfile):
        writepdb(self,pdbfile)


    def update(self):
        self.nresidues = 0
        self.natoms = 0
        self.nchains = len(self.chains)
        for chain in self.chains:
            natoms = 0
            for ires,residue in enumerate(chain.residues):
                residue.resid = ires+1
                natoms += residue.natoms
            chain.natoms = natoms
            chain.nresidues = len(chain.residues)
            self.nresidues += chain.nresidues
            self.natoms += natoms
        return


    def delwaters(self):
        waters = []
        for chain in self.chains:
            for ires,residue in enumerate(chain.residues):
                if residue.name in ['HOH','WAT']:
                    waters.append(ires)
            for water in reversed(waters):
                del chain.residues[water]
        return


    @staticmethod
    def addres(residues,residue,natoms,names,elements,coordinates,chain,backbone):
        _residue = Residue(residue,natoms)
        _residue.names = np.array(names)
        _residue.elements = np.array(elements)
        _residue.coordinates = np.array(coordinates)
        _residue.chain = chain
        _residue.backbone = backbone
        _residue.resid = len(residues) + 1
        residues.append(_residue)
        return


    @staticmethod
    def addchain(chains,chain,residues,natoms,resid,nmissing):
        _chain = Chain(chain)
        _chain.residues = copy.deepcopy(residues)
        _chain.natoms = natoms
        _chain.nresidues = resid
        chains.append(_chain)
        return [], 0 ,0 ,0


    def savessbond(self,ssbonds,residue,resid,nmissing,chain):
        if (self.nssbonds > 0) and (residue in ['CYS','CYX']):
            for issbond in range(self.nssbonds):
                if ((resid+nmissing == ssbonds[issbond][0]) and (chain == ssbonds[issbond][1])):
                        residue = 'CYX'
                        self.ssbonds[issbond][0] = resid
                        self.ssbonds[issbond][1] = chain
                elif ((resid+nmissing == ssbonds[issbond][2]) and (chain == ssbonds[issbond][3])):
                        residue = 'CYX'
                        self.ssbonds[issbond][2] = resid
                        self.ssbonds[issbond][3] = chain
        return residue


    def mutate(self,original,new):
        point_mutation(self,original,new)
        return


    def append(self,chain,residue,psi=None):
        try:
            _residue = resdict[residue]
        except:
            raise MyDockingError("There is no residue with name '{}'".format(residue))


        if psi is None:
            psi = -40.0
        elif isinstance(psi,str):
            psi = phi.lower()
            if psi == "alpha":
                psi = -40
            elif psi == "beta":
                psi = 130.0
            else:
                raise MyDockingError()

        for _chain in self.chains:
            if _chain.name == chain:
                newcoords = appendc(_chain,_residue,psi)
                natoms = len(_residue.coordinates)
                newres = Residue(residue,natoms)
                newres.names = _residue.elements[:,1]
                newres.coordinates = newcoords
                newres.elements = _residue.elements[:,0]
                newres.chain = chain
                newres.backbone = _residue.backbone
                newres.resid = len(_chain.residues) + 1
                _chain.residues.append(newres)
                break
        self.update()
        find_clashes_residue(newres,[self])
        return


    def prepend(self,chain,residue,phi=None):
        try:
            _residue = resdict[residue]
        except:
            raise MyDockingError("There is no residue with  name '{}'".format(residue))

        if phi is None:
            phi = -60.0
        elif isinstance(phi,str):
            phi = phi.lower()
            if phi == "alpha":
                phi = -60
            elif phi == "beta":
                phi = -140.0
            else:
                raise MyDockingError()

        for _chain in self.chains:
            if _chain.name == chain:
                newcoords = prependn(_chain,_residue,phi)
                natoms = len(_residue.coordinates)
                newres = Residue(residue,natoms)
                newres.names = _residue.elements[:,1]
                newres.coordinates = newcoords
                newres.elements = _residue.elements[:,0]
                newres.chain = chain
                newres.backbone = _residue.backbone
                newres.resid = len(_chain.residues) + 1
                _chain.residues.insert(0,newres)
                break
        self.update()
        find_clashes_residue(newres,[self])
        return


    def delchain(self,chain):
        newchains = []
        for i, _chain in enumerate(self.chains):
            if _chain.name == chain: continue
            newchains.append(_chain)
        self.chains = newchains
        self.update()
        return


    def findresidue(self,name):
        for _chain in self.chains:
            for residue in _chain.residues:
                if residue.name == name:
                    print("{}:{}{}".format(_chain.name,name,residue.resid))
        return


    def modify(self,original,modification):
        post_translational_modification(self,original,modification)
        return


    def dock(self,ligand,receptor,boxcenter=None,boxsize=10,output=None,flexible=None):
        dock_ligand(self,ligand,receptor,boxcenter,boxsize,output,flexible)
        return

    def protonate(self,pdbin=None,pdb=None,pqr=None,ph=7):
        # Check if pdb2pqr30 is in the path
        if which("pdb2pqr30") is None:
            raise MyDockingError("Cannot find PDB2PQR")
        if pdbin is None:
            pdbin = ".tmp.pdb"
            self.write_pdb(pdbin)
        if self.pdbid is not None:
            if pdb is None: _pdb = self.pdbid + "_H.pdb"
            if pqr is None: _pqr = self.pdbid + "_H.pqr"
        elif self.uniprotid is not None:
            if pdb is None: _pdb = self.uniprotid + "_H.pdb"
            if pqr is None: _pqr = self.uniprotid + "_H.pqr"
        elif self.filename is not None:
            if pdb is None: _pdb = self.filename[:-4] + "_H.pdb"
            if pqr is None: _pqr = self.filename[:-4] + "_H.pqr"
        else:
            if (pdb is None) or (pqr is None):
                raise MyDockingError("Provide a PDB and PQR filename for protonoation output")
        fh = open("pdb2pqr.log","w")
        subprocess.run(["pdb2pqr30",
            "--ff","AMBER",
            "--ffout","AMBER",
            "--pdb-output",_pdb,
            "--titration-state-method","propka",
            "--with-ph",str(ph),
            "-o",str(ph),
            "--protonate-all",
            pdbin, _pqr], stdout=fh, stderr=subprocess.STDOUT)
        fh.close()
        self.charge = 0
        with open(_pqr,"r") as fh:
            lines = fh.readlines()
        for line in lines:
            try:
                self.charge += float(line.split()[8])
            except:
                pass

        with open(_pdb,"r") as fh:
            self.pdbfile = fh.readlines()
        digestpdb(self,interactive=False,delwat=False,delhet=False)

        return
