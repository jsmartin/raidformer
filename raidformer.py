#! /usr/bin/python

import time
import optparse
import sys
from boto import ec2
import boto.utils
import pprint
from subprocess import Popen, PIPE, STDOUT
import string
import os.path
import glob

def runcmd(cmd):
    p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True)
    output = p.stdout.read()
    output.strip()
    return output

def attached_name(item):
    item = item.replace("sd","xvd")
    return item

def get_options():
    """ command-line options """

    usage = "usage: %prog [options]"
    OptionParser = optparse.OptionParser
    parser = OptionParser(usage)

    parser.add_option("-a", "--attach",  action="store_true",
            dest="attach", default=False, help="Do the volume creation and attachment.")
    parser.add_option("-c", "--count", action="store", type="int", \
            dest="count", help="Number of EBS volumes ")
    parser.add_option("-d", "--device", action="store", type="string", \
            dest="device", default="/dev/sdf",  help="block device to start with")
    parser.add_option("-f", "--filesystem", action="store", type="string", \
            dest="filesystem", default="ext4", help="filesystem type")
    parser.add_option("-l", "--logvol", action="store", type="string", \
            dest="logvol", default="LogVolData", help="Logical Volume Name")
    parser.add_option("-m", "--mountpoint", action="store", type="string", \
            dest="mountpoint", help="Mountpoint")
    parser.add_option("", "--md", action="store", type="string", \
            dest="md_device", default="/dev/md0", help="md device name ")
    parser.add_option("-r", "--raidlevel", action="store", type="int", \
            dest="raidlevel", help="RAID level")
    parser.add_option("-s", "--size", action="store", type="int", \
            dest="size", help="Size of EBS volumes ")
    parser.add_option("-t", "--test",  action="store_true",
            dest="test", default=False, help="Does a dry run of the mdadm lvm commands.")
    parser.add_option("", "--tag", action="store", type="string", \
            dest="tag", default="ebs_raid", help="Tag name for the ebs devices")
    parser.add_option("-v", "--volgroup", action="store", type="string", \
            dest="volgroup", default="VolGroupData", help="Volume Group Name")
    parser.add_option("-w", "--wipe",  action="store_true",
            dest="wipe", default=False, help="format the new filesystem")
    options, args = parser.parse_args()

    return options, args

def initialize_raid( cmds, md_device, raidlevel, count, attached_devices ):


    cmds.append("echo  Y | mdadm  --verbose --create  %s --level=%s --chunk=256 --raid-devices=%s %s" % ( md_device, str(raidlevel), str(count), ' '.join(attached_devices) ) )
    cmds.append("mdadm --detail --scan >  /etc/mdadm.conf")
    cmds.append("dd if=/dev/zero of=%s bs=512 count=1" % options.md_device )
    cmds.append("pvcreate %s" % options.md_device )
    return cmds

def initialize_filesystem(cmds, wipe, md_device, volgroup,logvol, format_cmds, filesystem, mountpoint):

    cmds.append("vgcreate %s %s" % ( volgroup, options.md_device  ) )
    cmds.append("lvcreate -l 100%%vg -n %s %s" % (logvol, volgroup) )
    if wipe == True:
        cmds.append("%s /dev/%s/%s" % (format_cmds[filesystem],volgroup, logvol))

    cmds.append('echo "/dev/%s/%s %s       %s    defaults        1 1" >> /etc/fstab' % (volgroup, logvol, mountpoint, filesystem) )
    cmds.append('mount %s' % mountpoint)
    if not os.path.isdir(mountpoint):
        print "creating mountpoint: %s" % mountpoint
        os.makedirs(mountpoint)
    return cmds

 
options, args = get_options()

format_cmds = {
    "ext4": "mkfs.ext4 -j"
}

#device lettering
#http://docs.amazonwebservices.com/AWSEC2/latest/UserGuide/ebs-attaching-volume.html

devices = [ '/dev/sdf', '/dev/sdg', '/dev/sdh', '/dev/sdi', '/dev/sdj', '/dev/sdk', '/dev/sdl', '/dev/sdm', '/dev/sdn', '/dev/sdo', '/dev/sdp' ]

if not options.device in devices:
  print "You must use a valid device.  See http://docs.amazonwebservices.com/AWSEC2/latest/UserGuide/ebs-attaching-volume.html."
  sys.exit(1)

if options.attach == True:
    if len(glob.glob(options.device)) > 0:
      print "You already have devices with that start with %s." % options.device
      sys.exit(1)
    
if os.path.exists(options.md_device):
  print "Device %s already exists." % options.md_device
  sys.exit(1)

my_devices = []

for n in range(1,options.count +1):
    my_devices.append(options.device + str(n) )

print my_devices

instance_data = boto.utils.get_instance_metadata()

ec2conn = ec2.connection.EC2Connection()

attached_devices = map(attached_name, my_devices)

vol_ids = []

if options.attach and not options.test:

    for device in my_devices:
        print "Working on ", device
        vol = ec2conn.create_volume(options.size, instance_data['placement']['availability-zone'])
        print "Created:", vol.id
        ec2conn.attach_volume(vol.id, instance_data['instance-id'], device)
        print "Attached:", vol.id
        vol_ids.append(vol.id)
        vol.add_tag("Name", options.tag)     

    
    for device in attached_devices:
        found = False
    
        while found == False:
        
            print "Waiting for %s to become available." % device
            if os.path.exists(device):
                print "%s has been found." % device
                break
            else:
                time.sleep(10)
    
    
cmds = []

if options.raidlevel:
    cmds = initialize_raid(cmds, options.md_device, options.raidlevel, options.count, attached_devices )

if options.wipe:
    cmds = initialize_filesystem(cmds, options.wipe, options.md_device, options.volgroup,options.logvol, format_cmds, options.filesystem, options.mountpoint)


for cmd in cmds:
    print 'Running:', cmd
    if options.test == False:
      output = runcmd(cmd)
      print output
