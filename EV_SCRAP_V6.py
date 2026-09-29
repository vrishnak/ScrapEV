import tkinter as tk
from gui.main_gui import ScrapApp

if __name__ == "__main__":
    # Point d'entrée principal de l'application V6
    root = tk.Tk()
    
    # Configuration du thème (optionnel)
    try:
        root.tk.call("source", "azure.tcl")
        root.tk.call("set_theme", "light")
    except:
        pass # Si le thème azure n'est pas présent, on utilise le thème par défaut de tkinter

    # Instanciation de notre interface graphique
    app = ScrapApp(root)
    
    # Lancement de la boucle d'événements de tkinter
    root.mainloop()
