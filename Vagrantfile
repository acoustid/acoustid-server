# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure(2) do |config|

  config.vm.box = "ubuntu/trusty64"

  config.vm.network "forwarded_port", guest: 5432, host: 5432 # postgresql
  config.vm.network "forwarded_port", guest: 6379, host: 6379 # redis
  config.vm.network "forwarded_port", guest: 5000, host: 5000 # web

  config.vm.provision "ansible" do |ansible|
    ansible.playbook = "admin/dev/ansible/setup.yml"
    ansible.sudo = true
  end

end
