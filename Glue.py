#!/usr/bin/env python
# encoding: utf-8

import sublime
import sublime_plugin
from sys import version_info
import subprocess
import sys
import os
import threading
import shlex

if version_info[0] == 3:
    from .GlueIO import FileReader
else:
    from GlueIO import FileReader

class GlueCommand(sublime_plugin.TextCommand):
    def __init__(self, *args, **kwargs):
        self.settings = sublime.load_settings('Glue.sublime-settings')
        self.stdout = ""
        self.stderr = ""
        self.exitcode = 1
        self.userpath = self.settings.get('glue_userpath')
        self.ps1 = self.settings.get('glue_ps1')
        self.current_dirpath = self.settings.get('glue_working_directory')
        self.current_filepath = ""
        self.attr_lock = threading.Lock() # thread lock for attribute reads/writes
        sublime_plugin.TextCommand.__init__(self, *args, **kwargs)

    def run(self, edit):
        # check the settings to see if working directory is set
        if len(self.current_dirpath) == 0:
            self.current_filepath = self.view.file_name() # if file is not yet saved, path is None
            if self.current_filepath:
                self.current_dirpath = os.path.dirname(self.current_filepath)
                # sublime.error_message("Glue : Please save this buffer as 'terminal.glue' in the working directory where you would like to launch Glue, then try again.")
        if self.current_dirpath:
            os.chdir(self.current_dirpath)
        else:
            ## handling when new buffer is launched and not saved to current project/directory
            ## TODO: allow user to specify start directory on fresh buffer launch
            self.current_dirpath = os.path.expanduser('~') # if open a buffer that is not saved, begin in home directory
            self.view.set_name('NEW.glue')
            os.chdir(self.current_dirpath)
            sublime.status_message('Glue: Current directory: ' + self.current_dirpath)
        self.view.window().show_input_panel(self.ps1 + ' ', '', self.muterun, None, None)

    def cleanup(self):
        self.current_dirpath = "" # clear the saved working directory path

    def muterun(self, user_command):
        # create a parsed command line string
        if version_info[0] == 3:
            com_args = shlex.split(user_command) # use shlex for command line handling in ST3 / Py3
        else:
            com_args = user_command.split() # use simple split on whitespace in ST2, Py2.6 does not support unicode in shlex

        # exit command
        if com_args[0] == "exit":
            self.cleanup() # run the cleanup method
            self.view.run_command('glue_writer', {'text': '', 'command': '', 'exit': True})
        elif com_args[0] == "cd":
            if len(com_args) > 1:
                change_path = com_args[1]
                if os.path.exists(change_path) and os.path.isdir(change_path):
                    os.chdir(change_path)
                    directory_change_abspath = os.getcwd()
                    dir_change_text = directory_change_abspath + '\n'
                    directory_change_cmd = "cd " + change_path
                    self.current_dirpath = directory_change_abspath
                    self.settings.set('working_directory', directory_change_abspath)
                    self.view.run_command('glue_writer', {'text': dir_change_text, 'command': directory_change_cmd, 'exit': False})
                else:
                    directory_change_cmd = "cd " + change_path
                    dirchange_error_message = "Directory path '" + change_path + "' does not exist\n"
                    self.view.run_command('glue_writer', {'text': dirchange_error_message, 'command': directory_change_cmd, 'exit': False})
        # glue commands
        elif com_args[0] == 'glue':
            glue_command = ' '.join(com_args)
            if len(com_args) > 1:
                # HELP Command
                if com_args[1] == "--help" or com_args[1] == "-h" or com_args[1] == "help":
                    help_text = get_help_text()
                    self.view.run_command('glue_writer', {'text': help_text, 'command': glue_command, 'exit': False})
                # CLEAR command
                elif com_args[1] == "clear":
                    self.view.run_command('glue_clear_editor')
                    # keeps the input panel open for more commands
                    self.view.run_command('glue')
                # OPEN command
                elif com_args[1] == "open":
                    if len(com_args) > 2:
                        self.view.window().run_command('glue_file_opener', {'current_dir': self.current_dirpath, 'file_list': com_args[2:]})
                        fileopen_text = "glue open command completed\n"
                        self.view.run_command('glue_writer', {'text': fileopen_text, 'command': glue_command, 'exit': False})
                    else:
                        missing_file_error_msg = "Please enter at least one filepath after the open command.\n"
                        self.view.run_command('glue_writer', {'text': missing_file_error_msg, 'command': glue_command, 'exit': False})
                # WCO command
                elif com_args[1] == "wco":
                    if len(com_args) > 2:
                        self.view.window().run_command('glue_file_wildcard_opener', {'current_dir': self.current_dirpath, 'match_pattern': com_args[2]})
                        fileopen_text = "glue wco command completed\n"
                        self.view.run_command('glue_writer', {'text': fileopen_text, 'command': glue_command, 'exit': False})
                    else:
                        missing_file_error_msg = "Please enter at least one filepath after the open command.\n"
                        self.view.run_command('glue_writer', {'text': missing_file_error_msg, 'command': glue_command, 'exit': False})
                elif com_args[1] == "test":
                    pass
                    # current_proj = str(dir(self.view.window()))
                    # current_proj = str(self.view.window().project_file_name())
                    # self.view.run_command('install_package')
                    # self.view.run_command('glue_writer', {'text': current_proj, 'command': glue_command, 'exit': False})
                else:
                    # USER COMMANDS
                    if len(com_args) > 1:
                        found_usercom = False
                        file_name = com_args[1] + '.gluc'
                        found_path = ''
                        uc_file_path = os.path.join('glue', file_name)
                        for i in range(6):
                            if not self.is_file_at_this_level(uc_file_path):
                                os.chdir(os.pardir)
                            else:
                                found_usercom = True
                                found_path = os.path.join(os.getcwd(), uc_file_path)
                                break
                        os.chdir(self.current_dirpath)
                        # Read the file to obtain the command
                        if found_usercom:
                            fr = FileReader(found_path)
                            user_command = fr.read_utf8()
                            # if arguments from command, add those in location indicated by the file
                            if len(com_args) > 2:
                                # arguments were included on the command line, pass them to the user command
                                arguments =  ' '.join(com_args[2:])
                            else:
                                # no additional arguments were included so pass empty string if there is an {{args}} tag
                                arguments = ''
                            user_command = user_command.replace('{{args}}', arguments)
                            self.muterun(user_command)
                        # Didn't find a glue command, provide error message
                        else:
                            bad_cmd_error_msg = "Glue could not identify that command.  Please try again.\n"
                            self.view.run_command('glue_writer', {'text': bad_cmd_error_msg, 'command': glue_command, 'exit': False})
            else:
                missing_arg_error_msg = "Glue requires an argument.  Please use 'glue help' for for more information.\n"
                self.view.run_command('glue_writer', {'text': missing_arg_error_msg, 'command': glue_command, 'exit': False})
        # execute the system command that was entered
        else:
            try:
                if len(com_args) > 0:
                    arguments = ' '.join(com_args[1:])
                else:
                    arguments = ''

                command = os.path.join(self.get_path(com_args[0]), com_args[0]) + " " + arguments
                t = threading.Thread(target=self.execute_command, args=(command, user_command))
                t.start() # launch the thread to execute the command
                self.progress_indicator(t) # provide progress indicator
                self.print_on_complete(t, user_command) # polls for completion of the thread and prints to editor
            except Exception as e:
                sys.stderr.write("Glue Plugin Error: unable to run the shell command.")
                raise e

    #------------------------------------------------------------------------------
    # [ is_file_at_this_level ] - returns boolean for presence of filepath
    #------------------------------------------------------------------------------
    def is_file_at_this_level(self, filepath):
        if os.path.exists(filepath) and os.path.isfile(filepath):
            return True
        else:
            return False

    #------------------------------------------------------------------------------
    # [ get_path method ] - find the correct path to the executable from the user's PATH setting
    #------------------------------------------------------------------------------
    def get_path(self, executable):
        if ':' in self.userpath:
            paths = self.userpath.split(':')
            for path in paths:
                test_path = os.path.join(path, executable)
                if os.path.isfile(test_path):
                    return path
                elif os.path.islink(test_path):
                    return os.path.dirname(os.path.realpath(test_path))
            # if the method did not return with found path, just return empty path and keep fingers crossed...
            return ''
        elif ';' in self.userpath:
            paths = self.userpath.split(';')
            for path in paths:
                test_path = os.path.join(path, executable)
                if os.path.isfile(test_path):
                    return path
                elif os.path.islink(test_path):
                    return os.path.dirname(os.path.realpath(test_path))
            # if the method did not return with found path, just return empty path and keep fingers crossed...
            return ''
        else:
            # there was one path in the setting, so return it as the proper path to executable
            return self.userpath

    #------------------------------------------------------------------------------
    # [ print_on_complete method ] - print to editor from main thread when cmd execution complete
    #  necessary for ST2 (not from ST3...)
    #------------------------------------------------------------------------------
    def print_on_complete(self, thread, user_command):
        if thread.is_alive():
            sublime.set_timeout(lambda: self.print_on_complete(thread, user_command), 20)
            return
        else:
            # command was successful
            if self.exitcode == 0:
                self.view.run_command('glue_writer', {'text': self.stdout, 'command': user_command})
            # command was not successful (non-zero exit status)
            else:
                self.view.run_command('glue_writer', {'text': self.stderr, 'command': user_command})

            # print to stdout as well
            self.print_response()

    #------------------------------------------------------------------------------
    # [ progress_indicator method ] - display progress indicator for long running processes
    #------------------------------------------------------------------------------
    def progress_indicator(self, thread, i=0, direction=1):
        if thread.is_alive():
            before = i % 8
            after = (7) - before
            if not after:
                direction = -1
            if not before:
                direction = 1
            i += direction
            self.view.set_status('glue_status_indicator', 'Glue: Running command [%s|%s]' % (' ' * before, ' ' * after))
            sublime.set_timeout(lambda: self.progress_indicator(thread, i, direction), 75)
            return
        else:
            self.view.erase_status('glue_status_indicator')
            sublime.status_message('Glue: Command completed.')

    #------------------------------------------------------------------------------
    # [ execute_command method ] - execute a system command
    #   run in a separate thread from muterun() method above
    #   assigns stdout stderr and exitcode in instance attributes
    #------------------------------------------------------------------------------
    def execute_command(self, command, user_command):
        # Python 3 version = Sublime Text 3 version
        if version_info[0] == 3:
            try:
                # execute the system command
                response = subprocess.check_output(command, stderr=subprocess.STDOUT, shell=True)
                # acquire thread lock on attribute data
                with self.attr_lock:
                    self.exitcode = 0
                    self.stdout = response.decode('utf-8')
                # self.view.run_command('glue_writer', {'text': self.stdout, 'command': user_command})
            except subprocess.CalledProcessError as cpe:
                # acquire thread lock on the attribute data
                with self.attr_lock:
                    self.stderr = cpe.output.decode('utf-8')
                    if cpe.returncode:
                        self.exitcode = cpe.returncode
                    else:
                        self.exitcode = 1
                # self.view.run_command('glue_writer', {'text': self.stderr, 'command': user_command})
            except Exception as e:
                raise e
        # Python 2 version = Sublime Text 2 version
        else:
            try:
                response = subprocess.Popen(command, shell=True,
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
                stdout, stderr = response.communicate()
                with self.attr_lock: # use the attribute lock (separate thread)
                    self.stdout = stdout.decode('utf-8')
                    self.stderr = stderr.decode('utf-8')
                    self.exitcode = response.returncode
            except Exception as e:
                raise e

    #------------------------------------------------------------------------------
    # [ print_response method ] - print a string to the stdout on ST console
    #------------------------------------------------------------------------------
    def print_response(self):
        with self.attr_lock:
            excode = self.exitcode
        if excode == 0:
            print(self.stdout)
        else:
            print(self.stderr)


#------------------------------------------------------------------------------
# [ GlueWriterCommand class ] - writes to a ST view
#------------------------------------------------------------------------------
class GlueWriterCommand(sublime_plugin.TextCommand):
    def __init__(self, *args, **kwargs):
        self.settings = sublime.load_settings('Glue.sublime-settings')
        self.ps1 = self.settings.get('glue_ps1')
        self.show_path = self.settings.get('glue_display_path')
        self.exit_message = self.settings.get('glue_exit_message')
        sublime_plugin.TextCommand.__init__(self, *args, **kwargs)

    def run(self, edit, text="", command="", exit=False):
        path_string = "[ " + os.getcwd() + " ]"
        if not exit:
            if self.show_path:
                command_line = self.ps1 + " " + path_string + " " + command + "\n"
            else:
                command_line = self.ps1 + " " + command + "\n"
            self.view.insert(edit, self.view.sel()[0].begin(), command_line)
            text = text + '\n'
            self.view.insert(edit, self.view.sel()[0].begin(), text)
            self.view.show(self.view.sel()[0].begin())
            # keeps the input panel open for more commands
            self.view.run_command('glue')
        else:
            # do not reopen the input panel with the run_command call above
            if self.show_path:
                exit_command = self.ps1 + " " + path_string + " exit\n"
            else:
                exit_command = self.ps1 + " exit\n"
            exit_string = self.exit_message + "\n"
            self.view.insert(edit, self.view.sel()[0].begin(), exit_command)
            self.view.insert(edit, self.view.sel()[0].begin(), exit_string)
            self.view.show(self.view.sel()[0].begin())
            return True


class GlueClearEditorCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        the_viewer = sublime.Region(0, self.view.size())
        self.view.erase(edit, the_viewer)


#------------------------------------------------------------------------------
# [ get_help_text function ] - returns the user help string
#------------------------------------------------------------------------------
def get_help_text():
    help_string = """
        __
 .-----|  .--.--.-----.
 |  _  |  |  |  |  -__|
 |___  |__|_____|_____|
 |_____|

Copyright 2014 Christopher Simpkins | MIT License

Glue joins your shell to Sublime Text in quasi-perfect harmony.

Usage

  <command> [option(s)]

  Enter a system command in the input panel at the bottom of your editor using the same syntax that you use in your terminal.  The standard output stream from the executable is printed in the active view of your editor after it returns.

  To quit Glue, submit the command 'exit'.

Commands
  Glue provides the following additional commands:

  glue clear               Clear the text in the Glue view
  glue help                Glue help
  glue open <path>         Open a file at <path> in the editor. Accepts multiple <path>
  glue wco <pattern>       Open file(s) with wildcard <pattern> in the editor

User Commands
  Create a directory named `glue` in the top level directory of your project and then add one or more files with the path `<PROJECT>/glue/<commandname>.gluc` in the directory.  Add a one-line command to the top line of the file and save it as plain text. Include one or more optional {{args}} tags anywhere in the command string in the file where you would like to insert any additional arguments that you include on the command line.

  Launch Glue and run your command with the following syntax:

     glue <commandname> [args]

  Your command is executed from your current working directory.

Navigation
  The working directory is initially set to the directory containing the buffer where you use Glue if you launch it with the sidebar menu item.  Change directories with the 'cd' command:

  cd <directory path>        Make `directory path` the working directory
  cd ..                      Make parent directory the working directory

  Note that if you are using a buffer that is not saved as the view for Glue (e.g. launching with the Command Palette), your working directory defaults to your user directory.

Issues
  Please submit bug reports on the GitHub repository @ https://github.com/chrissimpkins/glue/issues

"""
    return help_string


