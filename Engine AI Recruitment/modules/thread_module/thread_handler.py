# thread_handler.py
from threading import Thread
import logging
from flask import current_app

def run_in_thread(target, *args, **kwargs):
    """
    Utility function to run a target function in a separate thread.
    
    Parameters:
        target (callable): The function to run in a thread.
        *args: Arguments to pass to the function.
        **kwargs: Keyword arguments to pass to the function.
    """
    try:
        # Dapatkan app context saat ini
        app_context = current_app._get_current_object()

        # Wrapper function untuk menjalankan target di dalam context Flask
        def wrapped_target(*args, **kwargs):
            with app_context.app_context():
                target(*args, **kwargs)

        # Start the thread with the wrapped target function and arguments
        thread = Thread(target=wrapped_target, args=args, kwargs=kwargs)
        thread.start()
        return thread
    except Exception as e:
        logging.error(f"Error starting thread for {target.__name__}: {e}", exc_info=True)
        raise