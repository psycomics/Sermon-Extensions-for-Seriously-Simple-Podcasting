<?php
/*
Plugin Name: Sermon Extensions for Seriously Simple Podcasting
Description: Customises Seriously Simple Podcasting (mostly by use of filters) for podcasting Sermon Series.
Version:     0.0.22
Author:      Chris Spalding
License:     GPL2
License URI: https://www.gnu.org/licenses/gpl-2.0.html
*/

defined( 'ABSPATH' ) or die( 'No script kiddies please!' );

class ssp_sermon_extender {
    public function register_more_settings( $settings ) {
        $settings['feed-details']['fields'][] = array(
            'id' 			=> 'data_ep_title_template',
            'label'			=> __( 'Episode title template' , 'seriously-simple-podcasting-sermonex' ),
            'description'	=> __( 'The template for the title of each episode (not yet implemented)', 'seriously-simple-podcasting-sermonex' ),
            'type'			=> 'text',
            'default'		=> '${bible_passage}',
            'placeholder'	=> '${bible_passage}',
            'callback'		=> 'wp_strip_all_tags',
            'class'			=> 'text',
            );
        $settings['feed-details']['fields'][] = array(
            'id' 			=> 'data_service_name',
            'label'			=> __( 'Service name' , 'seriously-simple-podcasting-sermonex' ),
            'description'	=> __( 'A name for the service that might be used in comments', 'seriously-simple-podcasting-sermonex' ),
            'type'			=> 'text',
            'default'		=> '10:30',
            'placeholder'	=> '',
            'callback'		=> 'wp_strip_all_tags',
            'class'			=> 'text',
            );
        $settings['feed-details']['fields'][] = array(
            'id' 			=> 'data_service_time',
            'label'			=> __( 'Service time' , 'seriously-simple-podcasting-sermonex' ),
            'description'	=> __( 'Publish time', 'seriously-simple-podcasting-sermonex' ),
            'type'			=> 'text',
            'default'		=> '10:30',
            'placeholder'	=> '',
            'callback'		=> 'wp_strip_all_tags',
            'class'			=> 'text',
            );
        $settings['feed-details']['fields'][] = array(
            'id' 			=> 'data_comments_template',
            'label'			=> __( 'Template for comments' , 'seriously-simple-podcasting-sermonex' ),
            'description'	=> __( 'A template for your episode comments if empty', 'seriously-simple-podcasting-sermonex' ),
            'type'			=> 'textarea',
            'default'		=> 'A Sermon preached by ${preacher} on ${date}',
            'placeholder'	=> 'A Sermon preached by ${preacher} on ${date}',
            'callback'		=> 'wp_strip_all_tags',
            'class'			=> 'large-text',
            );
        $settings['feed-details']['fields'][] = array(
            'id' 			=> 'data_series_file_code',
            'label'			=> __( 'Series file code' , 'seriously-simple-podcasting-sermonex' ),
            'description'	=> __( 'The code following the date in the files for this series', 'seriously-simple-podcasting-sermonex' ),
            'type'			=> 'text',
            'default'		=> '',
            'placeholder'	=> '',
            'callback'		=> 'wp_strip_all_tags',
            'class'			=> 'text',
            );
        $settings['feed-details']['fields'][] = array(
            'id' 			=> 'data_series_file_template',
            'label'			=> __( 'Series file template' , 'seriously-simple-podcasting-sermonex' ),
            'description'	=> __( 'The formatting for the output file name', 'seriously-simple-podcasting-sermonex' ),
            'type'			=> 'text',
            'default'		=> '%Y-%m-%d${series_file_code}_{slug}',
            'placeholder'	=> '%Y-%m-%d${series_file_code}_${slug}',
            'callback'		=> 'wp_strip_all_tags',
            'class'			=> 'text',
            );
        

        return $settings;
    }

    public function register_more_options( $options ) {
		//get all the wordpress options, find the ones that start with 'ss_podcasting' and add them to the options array
		$all_options = wp_load_alloptions();
        foreach( $all_options as $name => $value ) {
            if(stristr($name, 'ss_podcasting')) {
                $options[$name] = array(
                    'desc'          => __( 'Seriously Simple Podcasting option whitelisted by SSP Sermon Extensions' ),
                    'readonly'      => true, //assuming that we won't need to write to these options from xmlrpc
                    'option'        => $name
			    );
			}
        }

        return $options;
    }
    
    public function add_more_episode_fields( $oldfields ) {
        //doing this with 2 arrays to merge the new ones in front of the old means new fields will be nearer the top of the page
        $newfields = array();
        //getting a copy of the date_recorded field from the oldfields
        $newfields['date_recorded'] = $oldfields['date_recorded'];
        //removing date_recorded from new fields
        unset( $oldfields['date_recorded'] );
        $newfields['bible_passage'] = array(
            'name' => __( 'Bible Passage:' , 'seriously-simple-podcasting-sermonex' ),
            'description' => __( 'The primary passage for this sermon.' , 'seriously-simple-podcasting-sermonex' ),
            'type' => 'text',
            'default' => '',
            'section' => 'info',
        );
        $newfields['episode_number'] = array(
            'name' => __( 'Episode number:' , 'seriously-simple-podcasting-sermonex' ),
            'description' => __( 'The part number in the series.' , 'seriously-simple-podcasting-sermonex' ),
            'type' => 'numeric',
            'default' => '',
            'section' => 'info',
        );
        $newfields['preacher'] = array(
            'name' => __( 'Preached by:' , 'seriously-simple-podcasting-sermonex' ),
            'description' => __( 'The person who delivered this sermon.' , 'seriously-simple-podcasting-sermonex' ),
            'type' => 'text',
            'default' => '',
            'section' => 'info',
        );
        $newfields['publish_now'] = array(
            'name' => __( 'Ready for Publish:' , 'seriously-simple-podcasting-sermonex' ),
            'description' => __( 'Ready for publish or for re-publish on next run.' , 'seriously-simple-podcasting-sermonex' ),
            'type' => 'checkbox',
            'default' => '',
            'section' => 'info',
        );
    
        $fields = array_merge(
            $newfields,
            $oldfields
            );
    
        return $fields;
    }
    
    public function add_more_episode_columns( $columns ) {
        $columns = array (
            'publish_now' => __( 'Ready for Publish:' , 'seriously-simple-podcasting-sermonex' ),
            'date_recorded' => __( 'Date Recorded', 'seriously-simple-podcasting'),
            'preacher' => __( 'Preacher' , 'seriously-simple-podcasting' ),
            'bible_passage' => __( 'Bible Passage' , 'seriously-simple-podcasting' ),
            'series' => __( 'Series' , 'seriously-simple-podcasting' ),
            'episode_number' => __( 'Part' , 'seriously-simple-podcasting' )
        );
               
        return $columns;
    }
        
    public function register_more_custom_columns( $column_name, $id ) {
        $custom_keys = get_post_custom_keys($id);
        if (in_array( $column_name, $custom_keys )) {
            echo get_post_meta($id, $key = $column_name, $single = true);
        }
    }    
            
    public function ssp_modify_number_of_posts_in_feed ( $n ) {
        return 18; 
    }
            
    public function __construct() {
        /*all these filters pass an array to the callback function*/
        //add the filter to add settings to SSP
        add_filter( 'ssp_settings_fields', array($this, 'register_more_settings') );

        //add the filter to whitelist db options for xmlrpc to access
        add_filter( 'xmlrpc_blog_options', array($this, 'register_more_options') );
            
        //add the filter for custom episode fields
        add_filter( 'ssp_episode_fields', array($this, 'add_more_episode_fields') );
        
        //show those fields in the overview:
        add_filter( 'ssp_admin_columns_episodes', array($this, 'add_more_episode_columns') );
        add_action( 'manage_posts_custom_column', array($this, 'register_more_custom_columns'), 10, 2 );
        
        add_filter( 'ssp_feed_number_of_posts', array($this, 'ssp_modify_number_of_posts_in_feed' ));


    }

}

//initialize all the above stuf
$ssp_sermonex = new ssp_sermon_extender;

//This bit allows podcast type posts to turn up in post_tag searches
add_filter('pre_get_posts', 'query_post_type');

function query_post_type($query) {
  if(is_category() || is_tag()) {
    $post_type = get_query_var('post_type');
	if($post_type)
	    $post_type = $post_type;
	else
	    $post_type = array('post','podcast');
    $query->set('post_type',$post_type);
	return $query;
    }
}

?>