BEGIN;
TRUNCATE TABLE tdps,repartiteurs,reglettes,opts RESTART IDENTITY CASCADE;
INSERT INTO opts(id,opt_label) VALUES(1,'FIC');
INSERT INTO reglettes(id,reglette_label) VALUES(1,'L/INX');
INSERT INTO repartiteurs(id,code_name,long_name,zip,nbr_salle,address) VALUES(1,'tst','REPARTITEUR FICTIF TEST UNIQUEMENT',99,1,'ADRESSE FICTIVE - AUCUN SITE REEL');
INSERT INTO tdps(id,rep,reglette_type,reglette_nbr,salle,rco,ferme,level,opts) VALUES(1,1,1,'1',1,1,1,1,1);
COMMIT;
