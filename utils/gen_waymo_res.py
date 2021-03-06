import os
import sys
import yaml
import pickle
import numpy as np
from tqdm import tqdm
import matplotlib.pyplot as plt
from utils import *

try:
    from c_gen_virtual_scan import gen_virtual_scan as range_projection
except:
    print("Using clib by $export PYTHONPATH=$PYTHONPATH:<path-to-library>")
    print("Currently using python-lib to generate range images.")

if __name__ == '__main__':
    # load config file
    config_filename = 'config/data_transform.yaml'
    if len(sys.argv) > 1:
        config_filename = sys.argv[1]

    if yaml.__version__ >= '5.1':
        config = yaml.load(open(config_filename), Loader=yaml.FullLoader)
    else:
        config = yaml.load(open(config_filename))

    # specify parameters
    data_type = config["type"]
    debug = config['debug']
    num_frames = config['num_frames']
    normalize = config['normalize']
    num_last_n = config['num_last_n']
    output_folder = config['Kitti_format_data_folder']
    visualize = config['visualize']

    range_image_params = config['range_image']

    scenes = os.listdir(output_folder)
    scenes.sort()
    
    for scene in scenes:
        scene_folder = os.path.join(output_folder, scene)
        # Poses
        poses_file = os.path.join(scene_folder, "poses.npy")
        if not exist(poses_file):
            print("Cannot find poses file", poses_file)
            continue
        poses_list = np.load(poses_file)
        poses = poses_list.reshape((poses_list.shape[0],4,4))

        # Lidars
        scans_folder = os.path.join(scene_folder, "lidars")
        if not exist(scans_folder):
            print("Cannot find lidar scan pc file", scans_folder)
            continue
        scans_paths = load_files(scans_folder)
        scans_paths.sort()

        # # Lables
        # labels_folder = os.path.join(scene_folder, "labels")
        # if not exist(labels_folder):
        #     print("Cant find labels folder")
        #     continue
        # labels_path = load_files(labels_folder)
        # labels_path.sort()

        # check frame number
        assert (len(scans_paths) == poses.shape[0])

        # Residual
        residual_image_folder = os.path.join(
            scene_folder, "residual_images_"+str(num_last_n))
        check_path(residual_image_folder)

        # Visualization
        if visualize:
            visualization_folder = os.path.join(scene_folder, "visualization")
            check_path(visualization_folder)

        # # This is used for innovusion prediction dataset
        # poses_list = []
        # pkl_file = open(scene_folder+"/pose.pkl", 'rb')
        # pkl = pickle.load(pkl_file)
        # for frame_pkl in pkl:
        #     poses_list.append(frame_pkl["pose"])

        for frame_idx in tqdm(range(len(scans_paths))):
            file_name = os.path.join(
                residual_image_folder, str(frame_idx).zfill(6))
            
            # frame_name = os.path.join(
            #     scans_folder, str(frame_idx).zfill(6))
            # label_name = os.path.join(
            #     labels_folder, str(frame_idx).zfill(6))
            # if not (exist(frame_name) and exist(label_name)):
            #     print ("Cant find frame or label", frame_idx)
            #     continue

            diff_image = np.full((range_image_params['height'], range_image_params['width']), 0,
                                 dtype=np.float32)  # [H,W] range (0 is no data)

            # for the first N frame we generate a dummy file
            if frame_idx < num_last_n:
                np.save(file_name, diff_image)
            else:
                # load current scan and generate current range image
                current_pose = poses[frame_idx]

                current_scan = load_vertex(scans_paths[frame_idx])

                current_range = range_projection(current_scan.astype(np.float32),
                                                 range_image_params['height'], range_image_params['width'],
                                                 range_image_params['fov_up'], range_image_params['fov_down'],
                                                 range_image_params['max_range'], range_image_params['min_range'])[:, :, 3]
                # load last scan, transform into the current coord and generate a transformed last range image
                last_pose = poses[frame_idx - num_last_n]
                last_scan = load_vertex(scans_paths[frame_idx - num_last_n])
                # (Xavier: align last scan to current coordinate)
                last_scan_transformed = np.linalg.inv(last_pose).dot(current_pose).dot(last_scan.T).T
                last_range_transformed = range_projection(last_scan_transformed.astype(np.float32),
                                                          range_image_params['height'], range_image_params['width'],
                                                          range_image_params['fov_up'], range_image_params['fov_down'],
                                                          range_image_params['max_range'], range_image_params['min_range'])[:, :, 3]
                # generate residual image
                valid_mask = (current_range > range_image_params['min_range']) & \
                    (current_range < range_image_params['max_range']) & \
                    (last_range_transformed > range_image_params['min_range']) & \
                    (last_range_transformed < range_image_params['max_range'])
                # normalize
                difference = np.abs(
                    current_range[valid_mask] - last_range_transformed[valid_mask])
                if normalize:
                    difference = np.abs(
                        current_range[valid_mask] - last_range_transformed[valid_mask]) / current_range[valid_mask]
                diff_image[valid_mask] = difference
                np.save(file_name, diff_image)
                # debug
                if debug:
                    fig, axs = plt.subplots(3)
                    axs[0].imshow(last_range_transformed)
                    axs[1].imshow(current_range)
                    axs[2].imshow(diff_image, vmin=0, vmax=10)
                    plt.show()
                # visualize
                if visualize:
                    fig = plt.figure(frameon=False, figsize=(16, 10))
                    fig.set_size_inches(20.48, 0.64)
                    ax = plt.Axes(fig, [0., 0., 1., 1.])
                    ax.set_axis_off()
                    fig.add_axes(ax)
                    ax.imshow(diff_image, vmin=0, vmax=1)
                    image_name = os.path.join(
                        visualization_folder, str(frame_idx).zfill(6))
                    plt.savefig(image_name)
                    plt.close()
