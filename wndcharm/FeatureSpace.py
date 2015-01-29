"""
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                                                                               
 Copyright (C) 2015 National Institutes of Health 

    This library is free software; you can redistribute it and/or              
    modify it under the terms of the GNU Lesser General Public                 
    License as published by the Free Software Foundation; either               
    version 2.1 of the License, or (at your option) any later version.         
                                                                               
    This library is distributed in the hope that it will be useful,            
    but WITHOUT ANY WARRANTY; without even the implied warranty of             
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU          
    Lesser General Public License for more details.                            
                                                                               
    You should have received a copy of the GNU Lesser General Public           
    License along with this library; if not, write to the Free Software        
    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA  
                                                                               
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                                                                               
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
 Written by:  Christopher Coletta <christopher.coletta [at] nih [dot] gov>
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""
import numpy as np
from .utils import output_railroad_switch, normalize_by_columns
from .FeatureVector import FeatureVector


def CheckIfClassNamesAreInterpolatable( classnames_list ):
    """N.B., this method takes only the first number it finds in the class label."""

    import re
    p = re.compile( r'(-?\d*\.?\d+)' )
    interp_coeffs = []
    for class_name in classnames_list:
        m = p.search( class_name )
        if m:
            interp_coeffs.append( float( m.group(1) ) )
        else:
            interp_coeffs = None
            break
    return interp_coeffs

#############################################################################
# class definition of FeatureSpace
#############################################################################
class FeatureSpace( object ):
    """An instance of FeatureSpace is one-half of a WND-CHARM classifier, the other half being the
    FeatureWeights instance.

    The FeatureSpace class is a container for sets of image descriptors, which are collected
    into Numpy matrices organized by image class or ground truth. FeatureSpaces are also used
    as containers for test images which have yet to be classified. FeatureSpaces can also be
    randomly Split() into two subset FeatureSpaces to be used for cross-validation of a
    classifier, one for training the other for testing.
    """

    # Used for parsing "File of Files" definition of FeatureSpace
    import re
    channel_col_finder = re.compile(r'(?P<path>.*?)?\{(?P<opts>.*?)?\}')
    channel_opt_finder = re.compile(r'(?:(?P<key>.+?)=)?(?P<value>.+)')

    #==============================================================
    def __init__( self, name=None, source_filepath=None, num_samples=None, num_samples_per_group=1,
                    num_features=None, discrete=True, feature_set_version=None ):
        """FeatureSpace constructor"""
        
        # Let F = # features for a given 5D ROI.
        # Let S = total # samples (rows) in a feature set.
        # Let C = # of discrete classes, if any, for a classification problem.
        # Let Si = # of samples in a given class whose index is i.
        # Let G = # tiles/ROIS in a sample group. Is 1 if no tiling.

        # BASIC DATA MEMBERS
        # -------------------------------------------
        #: type: string
        self.name = name

        #: type: string
        #: Path to FeatureSpace source/definition/origination file or directory.
        self.source_filepath = source_filepath

        #: type: FeatureSpace, or string containing 'self'
        #: By convention, the range of values are normalized on an interval [0,100].
        #: Reference to self or another FeatureSpace, indicating source of feature
        #: maxima/minima to transform feature space to normalized interval.
        self.normalized_against = None

        #: type: numpy.ndarray
        #: 2D numpy matrix with shape=(F,S) that contains all features.
        self.data_matrix = None
        #: If classification, per-class views into the feature matrix
        self.data_list = None

        #: @type: boolean
        #: Set to True when features packed into single matrix via internal
        self.data_matrix_is_contiguous = False
        
        #: The feature vector version contained in this FeatureSpace
        #: The major version must match for all feature vectors in the FeatureSpace
        #: The minor version must match also if it is one of the standard feature vectors (i.e. non-0)
        self.feature_set_version = feature_set_version

        self.feature_options = None
        self.tile_rows = None
        self.tile_cols = None

        #: Do the samples belong to discrete classes for supervised learning, or not
        #: (regression, clustering)
        self.discrete = discrete

        #: shape - supposed to work like numpy.ndarray.shape
        self.shape = None

        # SAMPLE METADATA DATA MEMBERS
        # N.B. Here data members are grouped into sets of two, the first being the "_contiguous"
        # version which is a simple list of length S, and the second being compound lists of lists,
        # the outer list being length C, inner lists of length Si, which are per-class convenience
        # views into their _contiguous data member counterpart.
        # -------------------------------------------

        #: FIXME: Eliminate in favor of len( self.samplenames_list )
        self.num_samples = num_samples

        #: A list of sample names in same row order as their samples appear in self.data_matrix.
        #: Corresponding lists of lists of sample names grouped by view.

        self._contiguous_samplenames_list = None
        self.samplenames_list = None

        #: By default, samples are independent/not grouped for splitting purposes
        self.num_samples_per_group = num_samples_per_group

        #: Keeps track of which samples are grouped together and must not be separated
        #: when FeatureSpace is split for cross-validation purposes
        self._contiguous_samplegroupid_list = None
        self.samplegroupid_list = None

        #: An intra-sample group tile/ROI index, max value = G
        self._contiguous_samplesequenceid_list = None
        self.samplesequenceid_list = None

        #: A list of floats with is the "target" vector for regression, interpolation, etc.
        self._contiguous_ground_truths = None
        self.ground_truths = None

        # List data members for discrete data whose len() is the number of classes
        #: List of strings which are the class names
        self.classnames_list = None
        #: float-ified versions of class labels, if applicable
        self.interpolation_coefficients = None
        #: Number of samples in each class
        self.classsizes_list = None


        # FEATURE METADATA DATA MEMBERS
        # -------------------------------------------
        #: FIXME: Eliminate in favor of len( self.featurenames_list )
        self.num_features = num_features

        #: block out some features for purposes of feature contribution analysis, et al.
        self.feature_mask = None

        #: A list of strings length M
        self.featurenames_list = None

        #: Contains pre-normalized feature maxima so feature space of this or other
        #: FeatureSpaces can be transformed.
        self.feature_maxima = None

        #: Contains pre-normalized feature minima so feature space of this or other
        #: FeatureSpaces can be transformed.
        self.feature_minima = None

        ### Now initialize array-like members if possible:
        if self.num_samples and self.num_features:
            self.shape = ( self.num_samples, self.num_features )
            self.data_matrix = np.empty( self.shape, dtype='double' )

        if self.num_samples:
            self._contiguous_samplenames_list = [None] * self.num_samples
            self._contiguous_samplegroupid_list = [None] * self.num_samples
            self._contiguous_samplesequenceid_list = [None] * self.num_samples
            self._contiguous_ground_truths = [None] * self.num_samples

        if self.num_features:
            self.featurenames_list = [None] * self.num_features

    #==============================================================
    def Derive( self, **kwargs ):
        """Make a copy of this FeatureSpace, except members passed as kwargs"""

        from copy import deepcopy
        new_obj = self.__class__()
        self_namespace = vars( self )
        new_obj_namespace = vars( new_obj )

        # Don't bother copying these "view" members which are rebuilt by self._RebuildViews()
        convenience_view_members = [ 'data_list', 'samplenames_list', 'samplegroupid_list',\
            'samplesequenceid_list', 'ground_truths' ]

        # Are all keys in kwargs valid instance attribute names?
        invalid_kwargs = set( kwargs.keys() ) - set( self_namespace.keys() )
        if len( invalid_kwargs ) > 0:
            raise ValueError( "Invalid keyword arg(s) to Derive: {0}".format( invalid_kwargs ) )

        # Go through all of self's members and copy them to new_fs
        # unless a key-val pair was passed in as kwargs
        for key in self_namespace:
            if key in convenience_view_members:
                continue
            if key in kwargs:
                new_obj_namespace[key] = kwargs[key]
            else:
                new_obj_namespace[key] = deepcopy( self_namespace[key] )
        new_obj._RebuildViews()
        return new_obj

    #==============================================================
    def Update( self, **kwargs ):
        """Replace instance attribute values with the ones passed as kwargs."""

        # FIXME: Should we call self._RebuildViews() at the end every time?
        self_namespace = vars( self )
        for key, val in kwargs.iteritems():
            if key in self_namespace:
                #if self_namespace[ key ] != None and self_namespace[ key ] != val:
                #    from warnings import warn
                #    warn( "Overwriting attrib {0} old val {1} new val {2}".format( key, self_namespace[ key ], val ) )
                self_namespace[ key ] = val
            else:
                raise AttributeError( 'No instance variable named "{0}" in class {1}'.format(
                  key, self.__class__.__name__ ) )
        return self

    #==============================================================
    def __deepcopy__( self, memo ):
        """Make a deepcopy of this FeatureSpace"""
        return self.Derive()

    #==============================================================
    @output_railroad_switch
    def Print( self, verbose=False ):
        """Prints out basic attributes about this training set, including name, path to
        source data, number and composition of image classes, number of features, etc."""

        print 'Summary of {0} "{1}":'.format( self.__class__.__name__ , self.name )
        if self.name != self.source_filepath:
            print 'source: "{0}"'.format( self.source_filepath )
        print 'Total samples: {0} ({1} groups, {2} samples/group)'.format( self.num_samples,
          len( set( self._contiguous_samplegroupid_list ) ), self.num_samples_per_group )
        print 'Total num features: {0}'.format( len( self.featurenames_list ) )
        print 'Feature Set Version: {0}'.format( self.feature_set_version )

        if self.discrete:
            rpt_str = '\tClass {0} "{1}": {2} samples ({3} groups)'
            if self.classnames_list is not None:
                for i, class_name in enumerate( self.classnames_list ):
                    print rpt_str.format( i, class_name, len( self.samplenames_list[i] ),
                            len( set( self.samplegroupid_list[i] ) ) )

        if verbose: # verbose implies print info for each sample
            if self.num_samples_per_group == 1:
                sample_metadata = \
                  zip( self._contiguous_samplenames_list, self._contiguous_ground_truths )
                header_str = "SAMP NAME\tGROUND TRUTH\n==============================================================="
                format_str = "{0}\t{1}"
            else:
                sample_metadata = zip( self._contiguous_samplenames_list, 
                            self._contiguous_samplegroupid_list, self._contiguous_samplesequenceid_list,
                            self._contiguous_ground_truths )
                header_str = "SAMP NAME\tGROUP INDEX\tTILE INDEX\tGROUND TRUTH\n===================================================================="
                format_str = "{0}\t{1:03d}\t{2:02d}\t{3}"

            print header_str
            for line_item in sample_metadata:
                print format_str.format( *line_item )
        print ""

    #==============================================================
    def __repr__( self ):
        """Prints out basic attributes about this training set, including name, path to
        source data, number and composition of image classes, number of features, etc."""

        outstr = '<' +str( self.__class__.__name__ ) + ' '
        outstr += '"{0}"'.format( self.name ) + ' '
        outstr += 'n_features=' + str( self.num_features ) + ' '
        outstr += 'n_total_samples=' + str( self.num_samples )
        if self.discrete:
            outstr += ' n_classes=' + str( self.num_classes ) + ' '
            outstr += 'samples_per_class=(' + ', '.join( [ '"{0}": {1}'.format( name, quant ) \
                            for name, quant in zip( self.classnames_list, self.classsizes_list ) ] ) + ')'
        outstr += '>'
        return outstr

    #==============================================================
    def CompatibleFeatureSetVersion( self, version ):
        """Note that if either minor version is 0 (i.e not a standard feature vector)
        we return true while in fact, the compatibility is unknown"""

        try:
            version = version.feature_set_version
        except AttributeError:
            # Assume version is the version string then.
            pass

        if self.feature_set_version is None or version is None:
            err_str = "Can't tell if FeatureSpace {0} is compatible with version {1} because "
            if self.feature_set_version is None and version is None:
                err_str += "both are null."
            elif self.feature_set_version is None:
                err_str += "the FS instance's version string is null."
            else:
                err_str += "input version string is null."
            raise AttributeError( err_str.format( self.name, version ) )

        their_major, their_minor = [ int(v) for v in version.split('.',1) ]
        our_major, our_minor = [ int(v) for v in self.feature_set_version.split('.',1) ]

        if( their_major != our_major ):
            return False
        if our_minor and their_minor and our_minor != their_minor:
            return False

        return True

    #==============================================================
    @classmethod
    def NewFromPickleFile( cls, pathname ):
        """Returns new instance of FeatureSpace build from a saved pickle file,
        with a filename ending in .fit.pickle"""

        path, filename = os.path.split( pathname )
        if filename == "":
            raise ValueError( 'Invalid pathname: {0}'.format( pathname ) )

        if not filename.endswith( ".fit.pickled" ):
            raise ValueError( 'Not a pickled FeatureSpace file: {0}'.format( pathname ) )

        print "Loading Training Set from pickled file {0}".format( pathname )
        the_training_set = None
        with open( pathname, "rb" ) as pkled_in:
            the_training_set = cls( pickle.load( pkled_in ) )

        # re-generate data_list views from data_matrix and classsizes_list
        if ("data_list" in the_training_set.__dict__):
            the_training_set.data_list = [0] * the_training_set.num_classes
            sample_row = 0
            for i in range( the_training_set.num_classes ):
                nrows = the_training_set.classsizes_list[i]
                the_training_set.data_list[i] = the_training_set.data_matrix[sample_row : sample_row + nrows]
                sample_row += nrows

        if (the_training_set.feature_set_version is None):
            the_training_set.feature_set_version = "1." + str(
                feature_vector_minor_version_from_num_features_v1.get( 
                    len(the_training_set.featurenames_list), 0 ) )

        return the_training_set

    #==============================================================
    def PickleMe( self, pathname=None ):
        """Pickle this instance of FeatureSpace and write to file whose path is optionally
        specified by argument "pathname" """

        outfile_pathname = ""
        if pathname != None:
            outfile_pathname = pathname
        else:
            # try to generate a path based on member source_filepath
            if self.source_filepath == None or self.source_filepath == "":
                raise ValueError( "Can't pickle this training set: its 'source_filepath' member"\
                        "is not defined, and you did not specify a file path for the pickle file." )
            if os.path.isdir( self.source_filepath ):
                # this trainingset was generated from a directory
                # naming convention is /path/to/topleveldir/topleveldir-options.fit.pickled
                root, top_level_dir = os.path.split( self.source_filepath )
                if self.feature_options != None and self.feature_options != "":
                    outfile_pathname = os.path.join( self.source_filepath, \
                                              top_level_dir + self.feature_options + ".fit.pickled" )
                else:
                    outfile_pathname = os.path.join( self.source_filepath, \
                                          top_level_dir + ".fit.pickled" )
            else:
                # was genearated from a file, could have already been a pickled file
                if self.source_filepath.endswith( "fit.pickled" ):
                    outfile_pathname = self.source_filepath
                elif self.source_filepath.endswith( ".fit" ):
                    outfile_pathname = self.source_filepath + ".pickled"
                else:
                    outfile_pathname = self.source_filepath + ".fit.pickled"    

        if os.path.exists( outfile_pathname ):
            print "Overwriting {0}".format( outfile_pathname )
        else:
            print "Writing {0}".format( outfile_pathname )

        # Since we may have both a data_matrix and views into it (data_list), we only want to store
        # one or the other.  Pickle is not smart enough to store numpy views as references.
        # We chose to store the data_matrix, setting data_list to [] if we have it
        # The views have to be reconstructed from the un-pickle using the classsizes_list
        self.ContiguousDataMatrix()
        data_list_copy = None
        if ("data_list" in self.__dict__):
            data_list_copy = self.data_list
            self.data_list = []
        with open( outfile_pathname, 'wb') as outfile:
            pickle.dump( self.__dict__, outfile, pickle.HIGHEST_PROTOCOL )

        # Restore the data_list
        if (data_list_copy):
            self.data_list = data_list_copy

    #==============================================================
    @classmethod
    def NewFromFitFile( cls, pathname, discrete=True, quiet=False,
            global_sampling_options=None, **kwargs ):
        """Helper function which reads in a c-chrm fit file.

        tile_options - an integer N -> NxN tile scheme, or a tuple (N,M) -> NxM tile scheme
        discrete_data - if false, try to interpret classes as continuous variable."""

        if not global_sampling_options:
            global_sampling_options = FeatureVector( **kwargs )

        import re
        from os.path import basename, split

        path, filename = split( pathname )
        if not filename.endswith( ".fit" ):
            raise ValueError( 'Not a .fit file: {0}'.format( pathname ) )

        if not quiet:
            print "Creating Training Set from legacy WND-CHARM text file file {0}".format( pathname )
        new_fs = cls()

        new_fs.source_filepath = filename
        new_fs.name = basename( filename )
        new_fs.discrete = discrete

        fitfile = open( pathname )

        name_line = False
        line_num = 0
        sample_count = 0

        new_fs.tile_rows = global_sampling_options.tile_num_rows
        new_fs.tile_cols = global_sampling_options.tile_num_cols
        new_fs.num_samples_per_group = new_fs.tile_rows * new_fs.tile_cols
        new_fs.global_sampling_options = global_sampling_options

        for line in fitfile:
            if line_num is 0:
                # 1st line: number of classes and feature vector version
                num_classes, feature_set_version = re.match('^(\S+)\s*(\S+)?$', line.strip()).group(1, 2)
                if feature_set_version is None:
                    feature_set_version = "1.0"
                new_fs.feature_set_version = feature_set_version
                num_classes = int( num_classes )
                new_fs.num_classes = num_classes
                new_fs.classsizes_list = [0] * num_classes
                new_fs.classnames_list = [0] * num_classes

            elif line_num is 1:
                # 2nd line: num features
                num_features = int( line )
                new_fs.num_features = num_features
                new_fs.featurenames_list = [None] * num_features
                if( feature_set_version == "1.0" ):
                    feature_set_version = "1." + str(
                        feature_vector_minor_version_from_num_features_v1.get ( num_features,0 ) )
                    new_fs.feature_set_version = feature_set_version

            elif line_num is 2:
                # 3rd line: number of samples
                num_samples = int( line )
                new_fs.num_samples = num_samples
                new_fs.shape = ( num_samples, num_features )
                new_fs.data_matrix = np.empty( new_fs.shape, dtype='double' )
                new_fs._contiguous_samplenames_list = [None] * num_samples

            elif line_num < ( num_features + 3 ):
                # Lines 4 through num_features contains the feature names
                #retval = wndchrm.FeatureNames.getFeatureInfoByName( line.strip() )
                #name = retval.name if retval else line.strip()
                name = line.strip()
                new_fs.featurenames_list[ line_num - 3 ] = name

            elif line_num == ( num_features + 3 ):
                # The line after the block of feature names is blank
                pass

            elif line_num < ( num_features + 4 + num_classes ):
                # Class labels
                class_index = line_num - num_features - 4
                new_fs.classnames_list[ class_index ] = line.strip()

            else:
                # Everything else after is a feature or a sample name
                # Comes in alternating lines of data, then path to sample original file (tif or sig)
                if not name_line:
                    # strip off the class identity value, which is the last in the array
                    features_string, class_index_string  = line.strip().rsplit( " ", 1 )
                    class_index = int( class_index_string ) - 1
                    new_fs.classsizes_list[ class_index ] += 1
                    # np.fromstring is a PIG, see timeit data elsewhere in code

                    new_fs.data_matrix[ sample_count ] = \
                      np.array( [ float(val) for val in features_string.split() ] )
                else:
                    new_fs._contiguous_samplenames_list[ sample_count ] = line.strip()
                    sample_count += 1
                name_line = not name_line

            line_num += 1

        fitfile.close()

        _retval = CheckIfClassNamesAreInterpolatable( new_fs.classnames_list )
        if _retval:
            # Numeric ground truth/target vector
            new_fs.interpolation_coefficients = _retval
            new_fs._contiguous_ground_truths = [ _retval[ class_index ] \
                for class_index in xrange( num_classes ) \
                  for i in xrange( new_fs.classsizes_list[ class_index ] ) ]
        else:
            # Just a string label ground truth
            new_fs._contiguous_ground_truths = [ new_fs.classnames_list[ class_index ] \
              for class_index in xrange( num_classes ) \
                for i in xrange( new_fs.classsizes_list[ class_index ] ) ]

        if new_fs.num_samples_per_group != 1:
            # sample sequence id = tile id
            # goes: [ 1, 2, 3, 4, 1, 2, 3, 4, ... ]
            new_fs._contiguous_samplesequenceid_list = [ i \
              for j in xrange( num_samples/new_fs.num_samples_per_group ) \
                for i in xrange( new_fs.num_samples_per_group ) ]
            # samples with same group id can't be split
            # goes: [ 1, 1, 1, 1, 2, 2, 2, 2, ... ]
            new_fs._contiguous_samplegroupid_list = [ j \
              for j in xrange( num_samples/new_fs.num_samples_per_group ) \
                for i in xrange( new_fs.num_samples_per_group ) ]
        else:
            new_fs._contiguous_samplesequenceid_list = [1] * num_samples
            new_fs._contiguous_samplegroupid_list = range( num_samples )

        print "Features version from .fit file: {0}".format( new_fs.feature_set_version )
        new_fs._RebuildViews()
        return new_fs

    #==============================================================
    def ToFitFile( self, path ):
        """Writes features to ASCII text file which can be read by classic wnd-charm."""
        fit = open( path, 'w' )

        # 1st line: number of classes and feature vector version
        fit.write( str(self.num_classes) + ' ' + self.feature_set_version + '\n' )
        # 2nd line: num features
        fit.write( str(self.num_features) + '\n' )
        # 3rd line: number of samples
        fit.write( str(self.num_samples) + '\n' )
        # Lines 4 through num_features contains the feature names
        for name in self.featurenames_list:
            fit.write( name + '\n' )
        # The line after the block of feature names is blank
        fit.write('\n')
        # Then all the Class labels
        for label in self.classnames_list:
            fit.write( label + '\n' )

        # In the fit file format, a sample's class membership is denoted by the final int
        # at the end of the line of features. A class index of 0 implies it belongs
        # to the UNKNOWN CLASS so in practical terms, fit file indexing starts at 1.
        if self.interpolation_coefficients is None and self.classnames_list is None:
            # For classless data, assign all samples to the UNKNOWN CLASS.
            class_indices = [0] * self.num_samples
        else:
            if self.interpolation_coefficients:
                ground_truth_class_vals = self.interpolation_coefficients
            else:
                ground_truth_class_vals = self.classnames_list

            class_indices = [None] * self.num_samples
            for i in xrange( self.num_samples ):
                try:
                    val = str( 1 + ground_truth_class_vals.index( self._contiguous_ground_truths[i] ) )
                except ValueError:
                    val = str( 0 )
                class_indices[i] = val

        # Finally, alternating lines of features and paths to sample original file (tif or sig)
        for i, sample_name in enumerate( self._contiguous_samplenames_list ):
            self.data_matrix[i].tofile( fit, sep=' ', format='%g' )
            # add class index of sample to end of features line
            fit.write( ' ' + class_indices[i] + '\n' )
            fit.write( sample_name + '\n' )

        fit.close()

    #==============================================================
    def _RebuildViews( self, reorder=False ):
        """Construct self's data members into either A) lists of per-class lists of 
        features/meature metadata which are optimized for classification-style machine 
        learning problems or B) single contiguous lists of data for regression-style problems.

        reorder - a sample was added out of order, reorder by class membership"""

        if reorder:
            raise NotImplementedError( "Sorry, this method doesn't handle sorting by classes yet" )

        if self.discrete is None:
            errmsg = 'FeatureSpace {0} "discrete" member hasn\'t been set. '.format( self )
            errmsg += 'Please set the flag on the object indicating classification vs. regression/clustering.'
            raise ValueError( errmsg )

        if self.discrete == True:
            self.data_list = [None] * self.num_classes
            self.samplenames_list = [None] * self.num_classes
            self.samplegroupid_list = [None] * self.num_classes
            self.samplesequenceid_list = [None] * self.num_classes
            if self._contiguous_ground_truths:
                self.ground_truths = [None] * self.num_classes

            class_bndry_index = 0
            for class_index in xrange( self.num_classes ):
                n_class_samples = self.classsizes_list[ class_index ]
                self.data_list[ class_index ] = \
                    self.data_matrix[ class_bndry_index : class_bndry_index + n_class_samples ]
                self.samplenames_list[ class_index ] = \
                    self._contiguous_samplenames_list[ class_bndry_index : class_bndry_index + n_class_samples ]
                self.samplegroupid_list[ class_index ] = \
                    self._contiguous_samplegroupid_list[ class_bndry_index : class_bndry_index + n_class_samples ]
                self.samplesequenceid_list[ class_index ] = \
                    self._contiguous_samplesequenceid_list[ class_bndry_index : class_bndry_index + n_class_samples ]
                if self._contiguous_ground_truths:
                    self.ground_truths[ class_index ] = \
                        self._contiguous_ground_truths[ class_bndry_index : class_bndry_index + n_class_samples ]

                class_bndry_index += n_class_samples

        else:
            self.data_list = self.data_matrix
            self.samplenames_list = self._contiguous_samplenames_list
            self.samplegroupid_list = self._contiguous_samplegroupid_list 
            self.samplesequenceid_list = self._contiguous_samplesequenceid_list
            self.ground_truths = self._contiguous_ground_truths

        self.data_matrix_is_contiguous = True
        return self

    #==============================================================
    @classmethod
    def NewFromDirectory( cls, top_level_dir_path, discrete=True, num_samples_per_group=1,
      quiet=False, global_sampling_options=None, write_sig_files_to_disk=True, **kwargs ):
        """@brief Equivalent to the "wndchrm train" command from the C++ implementation by Shamir.
        Read the the given directory and parse its structure for class membership.
        Populate a list of FeatureVector instances, then call helper functions to
        load/calculate features and populate this object."""

        if not global_sampling_options:
            global_sampling_options = FeatureVector( **kwargs )

        if not quiet:
            print "Creating Training Set from directories of images {0}".format( top_level_dir_path )

        samples = []
        tile_num_rows = global_sampling_options.tile_num_rows
        tile_num_cols = global_sampling_options.tile_num_cols

        from copy import deepcopy
        from os import walk
        from os.path import join, basename
        sample_group_count = 0
        for root, dirs, files in walk( top_level_dir_path ):
            if root == top_level_dir_path:
                if len( dirs ) <= 0:
                    # no class structure
                    filelist = [ join( root, _file ) for _file in files \
                                      if _file.endswith(('.tif','.tiff','.TIF','.TIFF')) ]
                    if len( filelist ) <= 0:
                        raise ValueError( 'No tiff files in directory {0}'.format( root ) )
                    for _file in filelist:
                        tile_position_index = col_index * tile_num_rows + row_index
                        for col_index in xrange( tile_num_cols ):
                            for row_index in xrange( tile_num_rows ):
                                fv = deepcopy( global_sampling_options )
                                fv.source_filepath = _file
                                fv.label = "UNKNOWN"
                                fv.tile_row_index = row_index
                                fv.tile_col_index = col_index
                                fv.Update()
                                samples.append( fv )
                        sample_group_count += 1
                    break
            else:
                # If we're here, we're down in one of the sub directories
                # This class's name will be "subdir" in /path/to/topleveldir/subdir
                filelist = [ join( root, _file ) for _file in files \
                                                    if _file.endswith(('.tif','.tiff','.TIF','.TIFF')) ]
                if len( filelist ) <= 0:
                    # Maybe the user hid them?
                    #raise ValueError( 'No tiff files in directory {0}'.format( root ) )
                    continue
                class_name = basename( root )
                for _file in filelist:
                    tile_position_index = col_index * tile_num_rows + row_index
                    for col_index in xrange( tile_num_cols ):
                        for row_index in xrange( tile_num_rows ):
                            fv = deepcopy( global_sampling_options )
                            fv.source_filepath = _file
                            fv.label = class_name
                            fv.tile_row_index = row_index
                            fv.tile_col_index = col_index
                            fv.Update()
                            samples.append( fv )
                    sample_group_count += 1

        # FIXME: Here's where the parallization magic can (will!) happen.
        [ fv.GenerateFeatures( write_sig_files_to_disk, quiet ) for fv in samples ]

        name = basename( top_level_dir_path )
        return cls._NewFromListOfFeatureVectors( samples, name=name,
               source_filepath=top_level_dir_path,
                     num_samples=None,
               num_samples_per_group=(tile_num_rows*tile_num_cols),
                     num_features=global_sampling_options.num_features,
               discrete=discrete, quiet=quiet )

    #==============================================================
    @classmethod
    def NewFromFileOfFiles( cls, pathname, discrete=True, quiet=False,
             global_sampling_options=None, write_sig_files_to_disk=True, **kwargs ):
        """Create a FeatureSpace from a file of files.

        The original FOF format (pre-2015) was just two columns, a path and a ground truth
        separated by a tab character. The extention to this format supports additional optional
        columns specifying additional paths and preprocessing options for a more complex
        feature space."""

        from os import getcwd
        from os.path import split, splitext, isfile, join
        from copy import deepcopy

        if not global_sampling_options:
            global_sampling_options = FeatureVector( **kwargs )

        if not quiet:
            print 'Loading {0} from file of files "{1}"'.format( cls.__name__, pathname )

        basepath, ext = splitext( pathname )
        dir_containing_fof, file_name = split( basepath )
        cwd = getcwd()

        num_fs_columns = None
        num_features = None
        feature_set_version = None

        # A FeatureSpace's samples in feature space need to be grouped by ground truth.
        # These variables help to determine if the samples listed in the input FOF are grouped.
        seen_ground_truths = set()
        previous_ground_truth = None
        current_ground_truth = None
        samples_grouped_by_ground_truth = True

        tile_num_rows = global_sampling_options.tile_num_rows
        tile_num_cols = global_sampling_options.tile_num_cols
        num_samples_per_group = tile_num_rows * tile_num_cols

        # Keeps track of the sample names to help organize like
        # samples into sample groups
        samp_name_to_samp_group_id_dict = {}

        def ReturnSampleGroupID( name ):
            if name not in samp_name_to_samp_group_id_dict:
                samp_name_to_samp_group_id_dict[ name ] = len(samp_name_to_samp_group_id_dict)
            return samp_name_to_samp_group_id_dict[ name ]

        samples = []
        fof = open( pathname )

        # There are a number of places to look for the existence of the files
        # specified via relative path.

        for line_num, line in enumerate( fof ):
            cols = line.strip().split('\t', 2)

            if samples_grouped_by_ground_truth:
                if current_ground_truth == None:
                    # first line
                    current_ground_truth = cols[1]
                else:
                    previous_ground_truth = current_ground_truth
                    current_ground_truth = cols[1]
                    if current_ground_truth != previous_ground_truth:
                        # crossed a class boundary, can't use previous ground truth anymore
                        seen_ground_truths.add( previous_ground_truth )
                    if current_ground_truth in seen_ground_truths:
                        # Samples not grouped, will require sample sorting.
                        # No need to keep checking.
                        samples_grouped_by_ground_truth = False

            # Classic two-column FOF format
            if len( cols ) < 3:

                # If first time through, set a flag to indicate this is an classic version FOF
                # Set number of sample columns = -1 so as not to confuse with columns 0, 1, 2, ...
                # in multichannel FOF format below.
                if num_fs_columns == None:
                    num_fs_columns = -1
                elif num_fs_columns != -1:
                    err_smg = "File {0}, line {1} has old-style two-column FOF format, while the other lines use the new-style format with {3} columns"
                    raise ValueError( err_msg.format( pathname, line_num, num_fs_columns + 3 ) )

                # Create a sampling opts template for this line in the FOF
                base_sample_opts = deepcopy( global_sampling_options )
                base_sample_opts.name = cols[0]
                base_sample_opts.label = cols[1]
                if not discrete:
                    base_sample_opts.ground_truth = float(cols[1])
                # Note only difference with base_sampling_opts in the 3+ col version code below
                # is the fs_col is always 0
                base_sample_opts.fs_col = 0

                if not isfile( cols[0] ):
                    # Try prepending current working directory
                    path_to_sample = join( cwd, cols[0] )
                    if not isfile( path_to_sample ):
                        # Try prepending path to this FOF
                        path_to_sample = join( dir_containing_fof, cols[0] )
                        if not isfile( path_to_sample ):
                            # Don't know what else to tell ya, pal.
                            raise ValueError( "Can't find sample \"{0}\"".format( cols[0] ) )
                else:
                    path_to_sample = cols[0]

                if path_to_sample.endswith('sig'):
                    # Not possible to tile over a feature vector, so it's just one and done here.
                    # Need to actually load the sig file here to tell how many features are contained
                    base_sample_opts.LoadSigFile( path_to_sample )
                    # Classic 2-col FOF listing sig path is an edgecase where we assign sample group id
                    # based on base prefix resulting from parsing out the sampling options ("-l", etc).
                    base_sample_opts.samplegroupid = ReturnSampleGroupID( base_sample_opts.basename )
                    samples.append( base_sample_opts )
                else:
                    base_sample_opts.source_filepath = path_to_sample
                    base_sample_opts.samplegroupid = ReturnSampleGroupID( cols[0] )
                    for col_index in xrange( tile_num_cols ):
                        for row_index in xrange( tile_num_rows ):
                            fv = deepcopy( base_sample_opts )
                            fv.Update( tile_row_index=row_index, tile_col_index=col_index )
                            samples.append( fv )
                # By now (after perhaps needing to load sig file) we know how many features in this sample
                num_feats_in_this_row = base_sample_opts.num_features
                if feature_set_version is None:
                    feature_set_version = base_sample_opts.feature_set_version
                elif feature_set_version != base_sample_opts.feature_set_version:
                    err_str = 'FOF line {0} has feature set version "{1}" that differs from rest "{1}"'
                    raise ValueError( err_str.format( line_num, base_sample_opts.feature_set_version,
                        feature_set_version ) )
            # NEW THREE-column FOF format:
            # Within "column 3" are sub-columns indicating channel options.
            # Generates a dict of FeatureSpace processing options for each column of
            # channel options found, which takes the form:
            # [optional path to tiff or sig file] {[optname1=val1;optname2=val2...]}
            else:
                num_feats_in_this_row = 0
                # tabs are ignored here, now the {} becomes the delimiter
                tabs_stripped_out = cols[2].translate( None, '\t' )
                for fs_col, m in enumerate( cls.channel_col_finder.finditer( tabs_stripped_out ) ):

                    # Start with a clean sample options template for each column
                    base_sample_opts = deepcopy( global_sampling_options )
                    base_sample_opts.name = cols[0]
                    base_sample_opts.samplegroupid = ReturnSampleGroupID( cols[0] )
                    base_sample_opts.label = cols[1]
                    if not discrete:
                        base_sample_opts.ground_truth = float(cols[1])
                    base_sample_opts.fs_col = fs_col

                    # Pull sampling options out of parentheses and load into template
                    col_finder_dict = m.groupdict()
                    opts_str = col_finder_dict['opts']
                    if opts_str:
                        col_opts = dict( [ mm.groups() for opt in opts_str.split(';') \
                                            for mm in cls.channel_opt_finder.finditer( opt ) ] )
                        if None in col_opts:
                            # value given without key is taken to be default channel
                            col_opts['channel'] = col_opts[None]
                            del col_opts[None]
                        base_sample_opts.Update( **col_opts )

                    # Now we deal with the path:
                    if col_finder_dict['path'] == None:
                        # If no path given in this channel column, implies string in cols[0]
                        # is the path upon with the options refer to.
                        # Doesn't make sense to have a sig file be in column 1
                        # then have channel options listed, so cols[0] must be a path to a tiff
                        path = cols[0]
                    else:
                        path = col_finder_dict['path']
                    if not isfile( path ):
                        # Try prepending current working directory
                        path_to_sample = join( cwd, path )
                        if not isfile( path_to_sample ):
                            # Try prepending path to this FOF
                            path_to_sample = join( dir_containing_fof, path )
                            if not isfile( path_to_sample ):
                                # Don't know what else to tell ya, pal.
                                raise ValueError( "Can't find sample \"{0}\"".format( path_to_sample ) )
                        path = path_to_sample

                    if path.endswith('sig'):
                        # Not possible to tile over a feature vector, so it's just one and done here
                        base_sample_opts.LoadSigFile( path )
                        samples.append( base_sample_opts )
                    else:
                        base_sample_opts.source_filepath = path
                        for col_index in xrange( tile_num_cols ):
                            for row_index in xrange( tile_num_rows ):
                                fv = deepcopy( base_sample_opts )
                                fv.Update( tile_row_index=row_index, tile_col_index=col_index )
                                samples.append( fv )
                    # By now (after perhaps needing to load sig file) we know how many features in this sample
                    num_feats_in_this_row += base_sample_opts.num_features

                # END loop over {} columns
                # FIXME: Fix the number of channel column options to be uniform for now,
                # may be allowable in the future to have different number of channel opt columns
                # say for when the user wants to pull a ROI for feature calculation for a certain
                # sample, but use the whole image for all the others.
                if num_fs_columns == None:
                    num_fs_columns = fs_col
                elif fs_col != num_fs_columns:
                    err_smg = "File {0}, line {1} has {2} channel cols, when the rest has {3}"
                    raise ValueError( err_msg.format( pathname, line_num, fs_col, num_fs_columns) )

                # FIXME: This is kinda kludgy since it doesn't evaluate major versions across columns
                if feature_set_version is None:
                    # More than one col = must be nonstandard FS
                    # Take major version sample opts from most recent col and call that this
                    # FeatureSapce's major version
                    if fs_col > 0:
                        feature_set_version = base_sample_opts.feature_set_version.split('.',1)[0] + '.0'
                    else:
                        base_sample_opts.feature_set_version

            # END if len( cols ) < 3

            # Num features across entire row, no matter the columns, must be uniform
            if num_features == None:
                num_features = num_feats_in_this_row
            elif num_features != num_feats_in_this_row:
                errmsg = 'FOF "{0}" row {1} calls for {2} features where previous rows ' + \
                    'call for {3} features.'
                raise ValueError(
                    errmsg.format( pathname, line_num, num_feats_in_this_row, num_features ) )

        # END iterating over lines in FOF
        fof.close()

        # FIXME: Here's where the parallization magic can (will!) happen.
        [ fv.GenerateFeatures( write_sig_files_to_disk, quiet ) for fv in samples ]

        assert num_features > 0

        return cls._NewFromListOfFeatureVectors( samples, name=file_name, source_filepath=pathname,
               num_samples=len(samp_name_to_samp_group_id_dict)*num_samples_per_group,
               num_samples_per_group=num_samples_per_group, num_features=num_features,
               feature_set_version=feature_set_version, discrete=discrete, quiet=quiet )

    #==============================================================
    @classmethod
    def _NewFromListOfFeatureVectors( cls, feature_vectors_list, name, source_filepath=None,
      num_samples=None, num_samples_per_group=1, num_features=None, feature_set_version=None,
      discrete=True, quiet=True ):
        """Input is list of FeatureVectors WHOSE FEATURES HAVE ALREADY BEEN CALCULATED.

        The arguments to this method call are intentionally very similar to the args of
        FeatureSpace.__init__()"""

        new_fs = cls( name, source_filepath, num_samples, num_samples_per_group,
                     num_features, discrete, feature_set_version )

        new_fs.Print()

        # For compound samples, e.g., multichannel, need to know the column offsets.
        # key: col index, value: index in data_matrix demarking rightmost feature for this column
        feature_set_col_offset = {}

        # column enumeration starts at 0, and need to know where the 0th column has its
        # LEFT boundary, i.e. what is column 0 - 1's right most boundary (exclusive):
        feature_set_col_offset[-1] = 0

        # Sort list of FeatureVectors by column so we can fill in data_matrix from left to right.
        for fv in sorted( feature_vectors_list, key=lambda fv: fv.fs_col ):
            if fv.values is None:
                raise ValueError( "Calls to this method require features to have already been calculated." )

            col_left_boundary_index = feature_set_col_offset[ fv.fs_col - 1 ]
            col_right_boundary_index = col_left_boundary_index + fv.num_features
            row_index = (fv.samplegroupid * num_samples_per_group) + fv.samplesequenceid

            # Fill in column metadata if we've not seen a feature vector for this col before
            if fv.fs_col not in feature_set_col_offset:
                feature_set_col_offset[ fv.fs_col ] = col_right_boundary_index
                new_fs.featurenames_list[ col_left_boundary_index : col_right_boundary_index ] = \
                  [ name.replace( '()', '({0})'.format( fv.fs_col ) ) for name in fv.featurenames_list ]

            # Fill in row metadata with FeatureVector data from column 0 only
            if fv.fs_col == 0: # (fs_col member must be > 0 and cannot be None)
                new_fs._contiguous_samplenames_list[ row_index ] = fv.name
                new_fs._contiguous_samplegroupid_list[ row_index ] = fv.samplegroupid
                new_fs._contiguous_samplesequenceid_list[ row_index ] = fv.samplesequenceid
                if discrete:
                    new_fs._contiguous_ground_truths[ row_index ] = fv.label
                else:
                    new_fs._contiguous_ground_truths[ row_index ] = fv.ground_truth

            new_fs.data_matrix[ row_index, col_left_boundary_index : col_right_boundary_index ] = \
              fv.values

        # alias:
        ground_truths = new_fs._contiguous_ground_truths

        if discrete:
            # Uniquify the sample group list, maintaining order of input sample group list.
            seen = set()
            seen_add = seen.add
            new_fs.classnames_list = [ x for x in ground_truths if not (x in seen or seen_add(x) ) ]
            new_fs.interpolation_coefficients = \
                CheckIfClassNamesAreInterpolatable( new_fs.classnames_list )
            new_fs.num_classes = len( new_fs.classnames_list )
            new_fs.classsizes_list = \
              [ ground_truths.count( label ) for label in new_fs.classnames_list ]

        if not discrete or new_fs.interpolation_coefficients is not None:
            new_fs._contiguous_ground_truths = [ float( val ) for val in ground_truths ]

        new_fs._RebuildViews()

        if not quiet:
            new_fs.Print()

        return new_fs

    #==============================================================
    def ContiguousDataMatrix( self ):
        """This method should be called to access the class data_matrix field.
        In the case where there are both views into this matrix (e.g. data_list) as well as the matrix itself,
        this method ensures that the data_matrix is a vstack of all data_lists
        After this call, the self.data_matrix field will be contiguous, and all of the views in data_list
        are consistent with it.
        """
        if not self.discrete:
            self._contiguous_samplenames_list = self.samplenames_list
            self._contiguous_samplegroupid_list = self.samplegroupid_list
            self._contiguous_samplesequenceid_list = self.samplesequenceid_list
            self._contiguous_ground_truths = self.ground_truths
            return self.data_matrix

        # If its already contiguous, or there are no data_lists, just return it
        if (self.data_matrix_is_contiguous or not self.data_list or not len (self.data_list) ):
            return self.data_matrix

        num_features = 0
        copy_class = 0
        copy_row = 0
        for class_mat in self.data_list:
            # Make sure all classes have the same number of features
            if (num_features and class_mat.shape[1] != num_features):
                raise ValueError ( "class index {0}:'{1}' has a different number of features than other classes ({3}).".format (
                    copy_class, self.classnames_list[i], num_features) )
            else:
                num_features = class_mat.shape[1]
            # if this flag is set in the numpy, then it is not a view.
            if class_mat.flags.owndata:
                # We don't need to keep going, all we need is the startpoint for the copy
                break
            copy_row += class_mat.shape[0]
            copy_class += 1

        if copy_class == len( self.data_list ):
            raise RuntimeError( "Internal error: ContiguousDataMatrix: none of the class views had their own data. Is the data_matrix contiguous already?" )

        # resize the matrix
        if self.data_matrix is not None:
            self.data_matrix.resize (self.num_samples, self.num_features)
        else:
            #print "called with empty data_matrix"
            self.data_matrix = np.empty ([ self.num_samples, self.num_features ], dtype='double')
            copy_class = 0
            copy_row = 0

        # In addition, keep a list of sample names corresponding to the 
        # rows in the contiguous feature matrix
        self._contiguous_samplenames_list = [ None ] * self.num_samples
        self._contiguous_samplegroupid_list = [ None ] * self.num_samples
        self._contiguous_samplesequenceid_list = [ None ] * self.num_samples
        self._contiguous_ground_truths = [ None ] * self.num_samples

        # We need to start copying at the first non-view class mat to the end.
        for class_index in range (copy_class, len (self.data_list)):
            #print "copy class"+str(class_index)
            nrows = self.data_list[class_index].shape[0]
            self.data_matrix[copy_row : copy_row + nrows] = np.copy (self.data_list[class_index])
            self.data_list[class_index] = self.data_matrix[copy_row : copy_row + nrows]
            self._contiguous_samplenames_list[copy_row : copy_row + nrows] = \
                                                         self.samplenames_list[class_index]
            self._contiguous_samplegroupid_list[copy_row : copy_row + nrows] = \
                                                         self.samplegroupid_list[class_index]
            self._contiguous_samplesequenceid_list[copy_row : copy_row + nrows] = \
                                                         self.samplesequenceid_list[class_index]
            self._contiguous_ground_truths[copy_row : copy_row + nrows] = \
                                                         self.ground_truths[class_index]
            copy_row += nrows

        self.data_matrix_is_contiguous = True
        return self.data_matrix

    #==============================================================
    def Normalize( self, input_feat_container=None, inplace=True, quiet=False ):
        """By convention, the range of feature values in the WND-CHARM algorithm are
        normalized on the interval [0,100]. Normalizing is useful in making the variation 
        of features human readable. Normalized samples are only comprable if they've been 
        normalized against the same feature maxima/minima."""

        if self.normalized_against:
            # I've already been normalized, and you want to normalize me again?
            raise ValueError( "{0} \"{1}\" has already been normalized against {2}.".format (
                self.__class__.__name__, self.name, self.normalized_against ) )

        newdata = {}

        if not input_feat_container:
            # Recalculate my feature space using my own maxima/minima
            if not quiet:
                print 'Normalizing {0} "{1}" ({2} images) against self'.format(
                    self.__class__.__name__, self.name, self.num_samples )
            mins = None
            maxs = None
            newdata['normalized_against'] = 'self'
        else:
            # Recalculate my feature space according to maxima/minima in input_feat_container
            if input_feat_container.featurenames_list != self.featurenames_list:
                err_str = "Can't normalize {0} \"{1}\" against {2} \"{3}\": Features don't match.".format(
                  self.__class__.__name__, self.name,
                    input_feat_container.__class__.__name__, input_feat_container.name )
                raise ValueError( err_str )
            if not self.CompatibleFeatureSetVersion( input_feat_container ):
                err_str = 'Incompatible feature versions: "{0}" ({1}) and "{2}" ({3})'
                raise ValueError( err_str.format( self.name, self.feature_set_version,
                    input_feat_container.name, input_feat_container.feature_set_version ) )
            
            if not quiet:
                print 'Normalizing "{0}" ({1} samples) against "{2}" ({3} samples)'.format(
                    self.name, self.num_samples, input_feat_container.name, input_feat_container.num_samples )

            # Need to make sure there are feature minima/maxima to normalize against:
            if not input_feat_container.normalized_against:
                input_feat_container.Normalize( quiet=quiet )

            mins = input_feat_container.feature_minima
            maxs = input_feat_container.feature_maxima
            newdata['normalized_against'] = input_feat_container

        newdata['data_matrix'] = np.copy( self.ContiguousDataMatrix() )
        newdata['feature_minima'], newdata['feature_maxima'] = \
            normalize_by_columns( newdata['data_matrix'], mins, maxs )

        if inplace:
            return self.Update( **newdata )._RebuildViews()
        return self.Derive( **newdata )

    #==============================================================
    def FeatureReduce( self, requested_features, inplace=False ):
        """Returns a new FeatureSpace that contains a subset of the data by dropping
        features (columns), and/or rearranging columns.

        requested_features := an object with a "featurenames_list" member
            (FeatureVector/FeatureSpace/FeatureWeights) or an iterable containing 
            strings that are feature names.

        Implementation detail: compares input "requested_features" to self.featurenames_list,
        and "requested_features" becomes the self.featurenames_list of the returned FeatureSpace."""

        try:
            requested_features = requested_features.featurenames_list
        except AttributeError:
            # assume it's already a list then
            pass

        # Check that self's faturelist contains all the features in requested_features
        selfs_features = set( self.featurenames_list )
        their_features = set( requested_features )
        if not their_features <= selfs_features:
            missing_features_from_req = their_features - selfs_features
            err_str = "Feature Reduction error:\n"
            err_str += '{0} "{1}" is missing '.format( self.__class__.__name__, self.name )
            err_str += "{0}/{1} features that were requested in the feature reduction list.".format(\
                    len( missing_features_from_req ), len( requested_features ) )
            err_str += "\nDid you forget to convert the feature names into their modern counterparts?"
            raise ValueError( err_str )

        num_features = len( requested_features )
        shape = ( self.num_samples, num_features )

        newdata = {}
        newdata[ 'shape' ] = shape
        newdata[ 'source_filepath' ] = self.source_filepath + "(feature reduced)"
        newdata[ 'name' ] = self.name + "(feature reduced)"
        newdata[ 'featurenames_list' ] = requested_features
        newdata[ 'num_features' ] = num_features
        data_matrix = np.empty( shape , dtype='double' )

        # Columnwise operations in Numpy are a pig:
        # %timeit thing = shuffle_my_cols[:,desired_cols]
        # 1 loops, best of 3: 3.5 s per loop
        #
        # Yikes. Slightly faster to do the copying yourself:
        # %%timeit
        # thing = np.empty( (numrows, numcols/2))
        # for new_index, old_index in enumerate( desired_cols ):
        #    thing[ :, new_index ] = shuffle_my_cols[ :, old_index ]
        # 1 loops, best of 3: 2.25 s per loop

        new_order = [ self.featurenames_list.index( name ) for name in requested_features ]
        for new_index, old_index in enumerate( new_order ):
            data_matrix[ :, new_index ] = self.data_matrix[ :, old_index ]
        newdata[ 'data_matrix' ] = data_matrix

        if self.feature_maxima is not None:
            newdata[ 'feature_maxima' ] = self.feature_maxima[ new_order ]
        if self.feature_minima is not None:
            newdata[ 'feature_minima' ] = self.feature_minima[ new_order ]

        # If the feature vectors sizes changed then they are no longer standard feature vectors.
        if self.feature_set_version is not None and num_features != self.num_features:
            newdata[ 'feature_set_version' ] = \
                    "{0}.0".format( self.feature_set_version.split('.',1)[0] )

        if inplace:
            return self.Update( **newdata )._RebuildViews()
        return self.Derive( **newdata )

    #==============================================================
    def SampleReduce( self, leave_in_samplegroupid_list=None, leave_out_samplegroupid_list=None,
        inplace=False):
        """Returns a new FeatureSpace that contains a subset of the data by dropping
        samples (rows), and/or rearranging rows.

        leave_in_sample_group_list := indicate the composition of the FeatureSpace to be returned.
            For discrete/classification FeatureSpaces:
            an iterable of iterables of sample group indices indicating desired sample groups;
            For continuous/regression FeatureSpaces:
            a iterable of desired sample group indices.

        leave_out_samplegroupid_list := a list containing sample group ids
            that should be left out
        Returns a near-deep copy of self including only the sample groups specified in the list.
        If no tiles, sample group reduces to just sample index."""

        if leave_in_samplegroupid_list is None and leave_out_samplegroupid_list is None:
            raise ValueError( 'Invalid input, both leave_in_samplegroupid_list and leave_out_samplegroupid_list were None')

        if self.normalized_against:
            errmsg = 'Cannot perform SampleReduce on FeatureSpace "{0}" '.format( self.name ) + \
                "because it's features have already been normalized and is therefore immutable."
            raise ValueError( errmsg )

        # Helper nested functions:
        #==================================
        def CheckForValidListOfInts( the_list ):
            """Items in list must be ints that are valid sample group ids for this FeatureSpace"""
            for item in the_list:
                if type( item ) is not int:
                    raise TypeError( "Input must be an int or a flat iterable containing only ints.")

            if not set( the_list ) < set( self._contiguous_samplegroupid_list ):
                msg = "Input contains sample group ids that aren't " + \
                            'contained in FeatureSpace "' + self.name + '", specifically: ' + \
                      str( sorted( list( set( the_list ) - set( self._contiguous_samplegroupid_list ) ) ) )
                raise ValueError( msg )

        def CheckForValidLISTOFLISTSOfInts( the_list ):
            try:
                for item in the_list:
                    if type( item ) is bool:
                        continue
                    elif type( item ) is list:
                        CheckForValidListOfInts( item )
            except TypeError:
                raise TypeError( "Input must be an iterable containing either booleans or iterables containing only ints.")

        def UniquifySansLeaveOutList( sg_list, leave_out ):
            seen = set()
            seen_add = seen.add
            uniq_sgids = [ x for x in sg_list  if not( x in seen or seen_add(x) ) and ( x not in leave_out) ]
            return uniq_sgids
        #==================================

        if leave_out_samplegroupid_list is not None:
            if type( leave_out_samplegroupid_list ) is int:
                leave_out_samplegroupid_list = [ leave_out_samplegroupid_list ]
            CheckForValidListOfInts( leave_out_samplegroupid_list )

            # build up a leave IN list, excluding the SGids that the user indicated
            if self.discrete:
                leave_in_samplegroupid_list = []
                for class_sgid_list in self.samplegroupid_list:
                    class_leave_in_sg_list = UniquifySansLeaveOutList( class_sgid_list, leave_out_samplegroupid_list )
                    leave_in_samplegroupid_list.append( class_leave_in_sg_list  )
            else:
                leave_in_samplegroupid_list = \
                  UniquifySansLeaveOutList( self.samplegroupid_list, leave_out_samplegroupid_list )
        else: # user provided leave in list
            if self.discrete:
                CheckForValidLISTOFLISTSOfInts( leave_in_samplegroupid_list )
            else: # if continuous
                if type( leave_in_samplegroupid_list ) is int:
                    leave_in_samplegroupid_list = [ leave_in_samplegroupid_list ]
                CheckForValidListOfInts( leave_in_samplegroupid_list )

        # Dummyproofing over.
        # Now we can count on the fact that leave_in_samplegroupid_list is defined,
        # either by the user or by the above code.

        # How many total training groups are requested?
        if self.discrete:
            try:
                total_num_sample_groups = \
                    sum( len( class_list ) for class_list in leave_in_samplegroupid_list if class_list )
            except TypeError:
                errmsg = 'Leave in list for discrete FeatureSpaces has to be a list (of length ' + \
                         'num_classes) of lists of ' + \
                         'desired sample group ids. Did you mean to pass it in as the leave OUT list?'
                raise TypeError( errmsg )
        else:
            total_num_sample_groups = len( leave_in_samplegroupid_list )

        total_num_samples = total_num_sample_groups * self.num_samples_per_group
        shape =  (total_num_samples, self.num_features)

        newdata = {}
        newdata[ 'shape' ] = shape
        newdata[ 'source_filepath' ] = self.source_filepath + " (subset)"
        newdata[ 'name' ] = self.name + " (subset)"
        newdata[ 'num_samples' ] = total_num_samples
        data_matrix = np.empty( shape, dtype='double' )
        _contiguous_samplegroupid_list = [None] * total_num_samples
        _contiguous_samplenames_list = [None] * total_num_samples
        _contiguous_samplesequenceid_list = [None] * total_num_samples
        _contiguous_ground_truths = [None] * total_num_samples

        j = 0
        if self.discrete:
            # If there's a False in the list of lists instead of a list, skip the class whose
            # index is in the same position as the False's index.
            newdata['classsizes_list' ] = classsizes_list = \
                [ self.num_samples_per_group * len(class_group_list) \
                    for class_group_list in leave_in_samplegroupid_list if class_group_list ]
            newdata[ 'num_classes' ] = num_classes = len( classsizes_list )

            # If user requests more classes than exists in self, that's ok, but you have to makeup
            # classnames. Throw a letter on the end of Class, and if they want more than
            # 26 classes, well they can inherit from this class and reimplement this function
            if num_classes <= self.num_classes:
                newdata[ 'classnames_list' ] = [ self.classnames_list[i] \
                  for i, num_groups in enumerate( leave_in_samplegroupid_list ) if num_groups ]
                if self.interpolation_coefficients:
                    newdata[ 'interpolation_coefficients' ] = [ self.interpolation_coefficients[i] \
                  for i, num_groups in enumerate( leave_in_samplegroupid_list ) if num_groups ]
            else:
                newdata[ 'classnames_list' ] = [ "Class" + letter for i, letter in \
                        zip( leave_in_samplegroupid_list, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' ) if i ]
                newdata[ 'interpolation_coefficients' ] = None
            for class_group_list in leave_in_samplegroupid_list:
                if not class_group_list:
                    continue
                for samp_group_id in class_group_list:
                    _contiguous_samplegroupid_list[ j : j + self.num_samples_per_group ] = \
                        [samp_group_id] * self.num_samples_per_group
                    j += self.num_samples_per_group
              
        else:
            for samp_group_id in leave_in_samplegroupid_list:
                _contiguous_samplegroupid_list[ j : j + self.num_samples_per_group ] = \
                    [samp_group_id] * self.num_samples_per_group
                j += self.num_samples_per_group

        assert( len( _contiguous_samplegroupid_list ) == total_num_samples )

        for i in xrange( 0, total_num_samples, self.num_samples_per_group ):
            groupid = _contiguous_samplegroupid_list[i]
            original_index = self._contiguous_samplegroupid_list.index( groupid )
            np.copyto( data_matrix[ i : i + self.num_samples_per_group ],
                            self.data_matrix[ original_index : original_index + self.num_samples_per_group ] )
            _contiguous_samplenames_list[ i : i + self.num_samples_per_group ] = \
               self._contiguous_samplenames_list[ original_index : original_index +  self.num_samples_per_group]
            _contiguous_samplesequenceid_list[ i : i + self.num_samples_per_group ] = \
               self._contiguous_samplesequenceid_list[ original_index : original_index +  self.num_samples_per_group]
            _contiguous_ground_truths[ i : i + self.num_samples_per_group ] = \
               self._contiguous_ground_truths[ original_index : original_index +  self.num_samples_per_group ]

        newdata[ 'data_matrix' ] = data_matrix
        newdata[ '_contiguous_samplenames_list' ] = _contiguous_samplenames_list
        newdata[ '_contiguous_samplesequenceid_list' ] = _contiguous_samplesequenceid_list
        newdata[ '_contiguous_ground_truths' ] = _contiguous_ground_truths
        newdata[ '_contiguous_samplegroupid_list' ] = _contiguous_samplegroupid_list

        if inplace:
            return self.Update( **newdata )._RebuildViews()
        return self.Derive( **newdata )

    #==============================================================
    def Split( self, train_size=None, test_size=None, random_state=True,
                    balanced_classes=True, quiet=False ):
        """Used for dividing the current FeatureSpace into two subsets used for classifier
        cross-validation (i.e., training set and test set).

        Analogous to Scikit-learn's cross_validation.train_test_split().

        Parameters (stolen directly from scikit-learn's documentation):

        test_size : float, int, or None (default is None)
                    If float, should be between 0.0 and 1.0 and represent the proportion
                    of the dataset to include in the test split (rounded up). If int, 
                    represents the absolute number of test samples. If None, the value is
                    automatically set to the complement of the train size. If train size 
                    is also None, test size is set to 0.25.

        train_size : float, int, or None (default is None)
                If float, should be between 0.0 and 1.0 and represent the proportion
                    of the dataset to include in the train split (rounded down). If int,
                    represents the absolute number of train samples. If None, the value
                    is automatically set to the complement of the test size.

        random_state : int or RandomState
                If true, generate a new random split. If int or Pseudo-random number
                    generator state used for random sampling. If value evaluates to false,
                    then do not randomize, but take the first samples in the order
                    the occur in the FeatureSpace/class."""

        # Step 1: Determine composition of split classes, i.e.,
        # figure out how many images/samples goes into the train and test sets respectively.

        if random_state:
            from numpy.random import RandomState

            if random_state is True:
                from numpy.random import shuffle
            elif type( random_state ) is RandomState:
                shuffle = random_state.shuffle
            elif type( random_state ) is int:
                shuffle = RandomState( random_state ).shuffle
            else:
                raise ValueError( 'Arg random_state must be an instance of numpy.random.RandomState, an int, or the value True')

        training_set_only = None

        if test_size == None:
            test_size = 0.25

        # ----- BEGIN NESTED FUNCTION -----------------------------------------------
        def CalcTrainTestSampleGroupMembership( samplegroupid_list, _max=None ):
            """Takes a list of sample group ids, and returns a two subset lists of ids whose lengths
            are determined by train_size and test_size.

            Raises ValueError if train_set/test_set params are not on interval 0<val<1 for float.

            train_size/test_size indicate number of sample groups desired, unless self.num_samples_per_group == 1,
            in which case they refer to samples.

            group_list = list containing sample group ids to be divided among training/test sets
            according to proportions prescribed in train_size & test_size (pulled from from outer scope)

            _max = Pare the list of sample group ids down to this length. Used to enforce balanced classes.
            
            Returns list of sample group ids to pass to SampleReduce()"""

            from math import ceil, floor

            # Uniquify the sample group list, maintaining order of input sample group list.
            seen = set()
            seen_add = seen.add
            unique_samplegroup_ids = [ x for x in samplegroupid_list if not (x in seen or seen_add(x) ) ]
            if _max and _max > len( unique_samplegroup_ids ):
                # Chop off the end
                unique_samplegroup_ids = unique_samplegroup_ids[ : _max ]

            num_samplegroups = len( unique_samplegroup_ids )

            # TEST SET SIZE:
            if type( test_size ) is int:
                if test_size < 0 or test_size >= num_samplegroups: # test sets of size 0 are allowed
                    errmsg = 'Arg test_size ({0}) must be 0 <= test_size < {1} (# images/sample groups).'
                    raise ValueError( errmsg.format( test_size, num_samplegroups ) )
                n_samplegroups_in_test_set = test_size
            elif type( test_size ) is float:
                if test_size < 0 or test_size >= 1: # test sets of size 0 are allowed
                    errmsg = 'Arg test_size fraction {0} must be 0 <= 1.0'
                    raise ValueError( errmsg.format( test_size ) )
                n_samplegroups_in_test_set = int( ceil( num_samplegroups * test_size ) )
            else:
                raise ValueError( 'Invalid input: test_size={0}'.format( test_size ) )

            # TRAIN SET SIZE:
            if type( train_size ) is int:
                if train_size < 0 or train_size >= num_samplegroups: # train sets of size 1 are allowed
                    errmsg = 'Arg train_size ({0}) must be 0 <= train_size < {1} (# images/sample groups).'
                    raise ValueError( errmsg.format( train_size, num_samplegroups ) )
                n_samplegroups_in_training_set = train_size
            elif type( train_size ) is float:
                if train_size < 0 or train_size >= 1: # train sets of size 1 are allowed
                    errmsg = 'Arg train_size fraction {0} must be 0 <= 1.0'
                    raise ValueError( errmsg.format( train_size ) )
                n_samplegroups_in_training_set = int( floor( num_samplegroups * train_size ) )
                if n_samplegroups_in_training_set <= 0:
                    raise ValueError( 'Please input train_size fraction such that there aren\'t 0 images (or sample groups) in training set' )
            elif train_size == None:
                n_samplegroups_in_training_set = num_samplegroups - n_samplegroups_in_test_set
            else:
                raise ValueError( 'Invalid input: train_size={0}'.format( test_size ) )

            if( n_samplegroups_in_training_set + n_samplegroups_in_test_set ) > num_samplegroups:
                    raise ValueError( 'User input specified train/test feature set membership contain more samples than are available.' )

            if random_state:
                shuffle( unique_samplegroup_ids )

            train_groups = sorted( unique_samplegroup_ids[ : n_samplegroups_in_training_set ] )

            if n_samplegroups_in_test_set:
                test_groups = sorted( unique_samplegroup_ids[ n_samplegroups_in_training_set : \
                            n_samplegroups_in_training_set + n_samplegroups_in_test_set ] )
            else:
                test_groups = False

            return train_groups, test_groups
        # ----- END NESTED FUNCTION -----------------------------------------------

        if not self.discrete: # If classless data:
            train_groups, test_groups = CalcTrainTestSampleGroupMembership( self.samplegroupid_list )

        else: # Discrete classes
            train_groups = []
            test_groups = []

            if balanced_classes:
                if self.num_samples_per_group > 1:
                    num_groups_per_class = [ num / self.num_samples_per_group for num in self.classsizes_list ]
                else:
                    num_groups_per_class = self.classsizes_list
                smallest_class_size = min( num_groups_per_class )
            else:
                smallest_class_size=None

            for class_index in xrange( self.num_classes ):
                try:
                    class_train_groups, class_test_groups = \
                      CalcTrainTestSampleGroupMembership( self.samplegroupid_list[class_index], _max=smallest_class_size  )
                except ValueError as e:
                    addl_msg = "Error with class index " + str(class_index) + \
                               '. For discrete FeatureSpaces (with classes), train_size and test_size' + \
                               ' are evaluated per-class. '
                    raise ValueError( addl_msg + e.message )
                else:
                    train_groups.append( class_train_groups )
                    test_groups.append( class_test_groups )                    

            if not any( test_groups ):
                training_set_only = True

        training_set = self.SampleReduce( train_groups, inplace=False )
        if not quiet:
            training_set.Print()
        if training_set_only:
            return training_set

        test_set = self.SampleReduce( test_groups, inplace=False )
        if not quiet:
            test_set.Print()
        return training_set, test_set

    #==============================================================
    def RemoveClass( self, class_index ):
        """For a future relase."""
        raise NotImplementedError()
    #==============================================================
    def ScrambleGroundTruths( self ):
        """For a future release. Produce an instant negative control training set"""
        raise NotImplementedError()

# END FeatureSpace class definition
