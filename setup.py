from setuptools import setup

setup(
        name='ptmpsi',
        description='A Python Package to Facilitate the Computational Investigation of Post-Translational Modification on Protein Structures and Their Impacts on Dynamics and Functions'
        version='0.1',
        author='Daniel Mejia-Rodriguez',
        author_email='daniel.mejia@pnnl.gov',
        install_requires=[
            'pytest',
            'numpy', 
            'networkx',
            'pandas',
            'scipy', 
            'rdkit', 
            'meeko', 
            'xyz2mol @ git+https://github.com/jensengroup/xyz2mol.git ',
            'pdb2pqr',
            'future',
            'pymbar',
            'matplotlib',
            'lxml',
            'torsiondrive @ git+https://github.com/dmejiar/torsiondrive.git@nwchem ',
            'forcebalance @ git+https://github.com/dmejiar/forcebalance.git@ptmflow '
        ],
    )
