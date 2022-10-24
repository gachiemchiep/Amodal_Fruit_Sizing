# You may need to restart your runtime prior to this, to let your installation take effect
# Some basic setup:
# Setup detectron2 logger
import detectron2
from detectron2.utils.logger import setup_logger
setup_logger()

# import some common libraries
import numpy as np
np.seterr(divide='ignore', invalid='ignore')
#from numpy.linalg import inv
import os
import cv2
#import random
import csv
#import json
#from tqdm import tqdm
#import time
#from tqdm import trange


# import some miscellaneous libraries
from utils import visualize

# import some common detectron2 utilities
from detectron2 import model_zoo
from detectron2.engine import DefaultPredictor
from detectron2.config import get_cfg
from detectron2.utils.visualizer import Visualizer
from detectron2.data import DatasetCatalog,MetadataCatalog
from detectron2.engine import DefaultTrainer
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.pylab as pylab

from utils import dataset_preparation, utils_diameter, utils_eval
import argparse

pylab.rcParams['figure.figsize'] = 10,10

def imshow(img):
    plt.imshow(img[:, :, [2, 1, 0]])
    plt.axis("off")
    plt.show()

def imshow_original_amodal_instance(img, amodal, instance):
    f, axarr = plt.subplots(1, 3)
    axarr[0].imshow(img[:, :, [2, 1, 0]])
    axarr[0].axis("off")
    axarr[1].imshow(amodal[:, :, [2, 1, 0]])
    axarr[1].axis("off")
    axarr[2].imshow(instance[:, :, [2, 1, 0]])
    axarr[2].axis("off")
    plt.waitforbuttonpress(0)
    plt.close()

def load_dataset_dicts(dataset_path, split):
    dataset_dicts_file = os.path.join(dataset_path, split + '_dataset_dicts.npy')
    print('Loading '+split+' DATASET...')
    if not os.path.exists(dataset_dicts_file):
        print('Preparing '+split+ ' DATASET...')
        dataset_dicts = dataset_preparation.get_AmodalFruitSize_dicts(dataset_path,split)
        np.save(dataset_dicts_file,np.array(dataset_dicts))
    dataset_dicts = np.load(dataset_dicts_file,allow_pickle=True)
    try:
        DatasetCatalog.register("AmodalFruitSize_"+split, lambda d=split: dataset_dicts)
    except:
        print("AmodalFruitSize_"+split+" is already registered!")
    dataset_metadata = MetadataCatalog.get("AmodalFruitSize_"+split)
    return dataset_dicts, dataset_metadata

def parse_args():
    parser = argparse.ArgumentParser(description='Evaluate detection')
    parser.add_argument('--experiment_name',dest='experiment_name',default='apple_WUR')
    parser.add_argument('--test_name',dest='test_name',default='190621-Tree27_E_fl24')
    parser.add_argument('--dataset_path',dest='dataset_path',default="/mnt/gpid07/users/jordi.gene/amodal_segmentation/data/apple_WUR/")
    parser.add_argument('--output_dir',dest='output_dir',default='./output/',help='name of the directory where to save the output results')
    parser.add_argument('--weights',dest='weights',default='/mnt/gpid07/users/jordi.gene/amodal_segmentation/code/sizecnn/output/trial01/model_0002999.pth')
    parser.add_argument('--nms_thr',dest='nms_thr',default=0.1)
    parser.add_argument('--conf',dest='conf',default=0)
    args = parser.parse_args()
    return args


if __name__ == '__main__':

    ## Read arguments parsed
    args = parse_args()

    experiment_name  = args.experiment_name
    test_name        = args.test_name
    dataset_path     = os.path.join(args.dataset_path,test_name)
    weights_file     = args.weights
    nms_thr          = float(args.nms_thr)
    confidence_score = float(args.conf)
    output_dir      = args.output_dir

    cfg = get_cfg()
    cfg.merge_from_file(model_zoo.get_config_file("COCO-InstanceSegmentation/mask_orcnn_X_101_32x8d_FPN_3x.yaml"))
    cfg.MODEL.ROI_HEADS.NUM_CLASSES = 1  # only has one class (apple)

    #cfg.OUTPUT_DIR = "./output/"+str(experiment_name)
    cfg.OUTPUT_DIR = output_dir+str(experiment_name)
    cfg.MODEL.WEIGHTS = weights_file
    cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = confidence_score   # set the testing threshold for this model
    #cfg.MODEL.ROI_HEADS.NMS_THRESH_TEST = 0.01
    cfg.MODEL.ROI_HEADS.NMS_THRESH_TEST = nms_thr
    cfg.DATASETS.TEST = ("AmodalFruitSize_test",)

    predictor = DefaultPredictor(cfg)
    output_dir = cfg.OUTPUT_DIR
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)
    output_dir = os.path.join(output_dir,test_name)
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)
    output_per_image_dir = os.path.join(output_dir,'txt_per_image')
    if not os.path.exists(output_per_image_dir):
        os.mkdir(output_per_image_dir)

    if os.path.exists(os.path.join(output_dir,'diameter_results.txt')):
        os.remove(os.path.join(output_dir,'diameter_results.txt'))

    dataset_metadata = MetadataCatalog.get("AmodalFruitSize_test")


    dict_info_txt = {}
    focal_length_dict = {}
    f = open(os.path.join(dataset_path,'focal_length.txt'))
    for row in csv.reader(f):
        focal_length_dict[row[0]]=float(row[1])

    for r, d, f in os.walk(os.path.join(dataset_path,'images')):
        for file in f:
            if file.endswith(".png") or file.endswith(".jpg") or file.endswith(".JPG"):
                print(os.path.join(r, file))
                img = cv2.imread(os.path.join(r, file))
                depth_map = np.load(os.path.join(dataset_path,'depth_maps',file[:-4]+'.npy'))
                outputs = predictor(img)
                predictions = outputs["instances"].to("cpu")
                diameters, occlusions = utils_diameter.amodal_diameter_estimation(depth_map, predictions, focal_length_dict[file])
                scores = predictions.scores.tolist()
                pred_instances = np.asarray(predictions.pred_visible_masks)
                pred_amodals = np.asarray(predictions.pred_masks)
                pred_boxs = predictions.pred_boxes.tensor.numpy()
                if os.path.exists(os.path.join(output_per_image_dir,file[:-4]+'.txt')):
                    os.remove(os.path.join(output_per_image_dir,file[:-4]+'.txt'))

                for j, pred_instance in enumerate(pred_instances):
                    if pred_instance.sum()>0 and predictions.pred_masks[j].sum()>0:
                        poly_txt_inst = utils_diameter.extract_polys(pred_instance)
                        poly_txt_amod = utils_diameter.extract_polys(pred_amodals[j])
                        dict_info_txt['instance_all_points_x'] = str(poly_txt_inst[0]['all_points_x']).replace('\n', '')
                        dict_info_txt['instance_all_points_y'] = str(poly_txt_inst[0]['all_points_y']).replace('\n', '')
                        dict_info_txt['amodal_all_points_x'] = str(poly_txt_amod[0]['all_points_x']).replace('\n', '')
                        dict_info_txt['amodal_all_points_y'] = str(poly_txt_amod[0]['all_points_y']).replace('\n', '')
                        dict_info_txt['conf'] = str(scores[j])
                        dict_info_txt['diam'] = str(diameters[j])
                        dict_info_txt['occ'] = str(occlusions[j])

                        with open(os.path.join(output_per_image_dir,file[:-4]+'.txt'), 'a+') as f:
                            f.write("\n")
                            f.write(
                                dict_info_txt['diam'] + '|' + dict_info_txt['occ'] + '|' + dict_info_txt['conf'] + '|' +
                                dict_info_txt['instance_all_points_x'] + '|' + dict_info_txt['instance_all_points_y'] + '|' +
                                dict_info_txt['amodal_all_points_x'] + '|' + dict_info_txt['amodal_all_points_y'])

                        with open(os.path.join(output_dir,'diameter_results.txt'), 'a+') as f:
                            f.write("\n")
                            f.write(file + '|' + dict_info_txt['diam'] + '|' + dict_info_txt['occ'] + '|' + dict_info_txt['conf'])









