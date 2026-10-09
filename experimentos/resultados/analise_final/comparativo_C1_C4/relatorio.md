# Comparação definitiva C1–C4

## Fontes e metodologia

Fontes exclusivas: os quatro agregados.csv individuais. São conferidas 116 linhas por cenário, nove combinações e três repetições declaradas por combinação (27 por cenário). Não são reestimadas as estatísticas das execuções, reunidas latências individuais ou incluídas tentativas inválidas.

| Cenário | vCPUs | RAM (GiB) | Workers |
|---|---:|---:|---:|
| C1 | 1 | 1 | 1 |
| C2 | 1 | 2 | 1 |
| C3 | 2 | 1 | 2 |
| C4 | 2 | 2 | 2 |

Configurações acima são as informadas para o experimento, não medições adicionais. Média e DP amostral são reproduzidos das fontes; n válido é mostrado por métrica. Ausentes permanecem ausentes. A média dos p95 das repetições não é o p95 de requisições reunidas. As barras de erro não são intervalos de confiança. A consistência algébrica de média/extremos/DP é verificada sem publicar repetições reconstruídas.

Diferença absoluta = média comparada − média base; percentual = 100 × diferença / média base. Não há percentual quando a base é zero ou algum valor está ausente. Para CPU, a diferença absoluta é em pontos percentuais; o percentual relativo é outra grandeza. Não são calculados testes de significância nem intervalos de confiança de diferenças a partir dos resumos.

## Tabelas comparativas

### vazao_rps — req/s

| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |
|---|---:|---|---|---|---|
| cpu | 1 | 3.851 ± 0.049 (n=3) | 3.835 ± 0.029 (n=3) | 4.231 ± 0.084 (n=3) | 4.282 ± 0.027 (n=3) |
| cpu | 2 | 3.818 ± 0.077 (n=3) | 3.827 ± 0.022 (n=3) | 8.428 ± 0.077 (n=3) | 8.462 ± 0.094 (n=3) |
| cpu | 5 | 3.821 ± 0.101 (n=3) | 3.550 ± 0.293 (n=3) | 7.640 ± 0.067 (n=3) | 7.607 ± 0.139 (n=3) |
| cpu | 10 | 3.968 ± 0.026 (n=3) | 3.484 ± 0.093 (n=3) | 6.672 ± 0.345 (n=3) | 6.769 ± 0.052 (n=3) |
| io | 1 | 5.343 ± 0.089 (n=3) | 5.429 ± 0.036 (n=3) | 5.210 ± 0.082 (n=3) | 5.014 ± 0.035 (n=3) |
| io | 2 | 5.635 ± 0.170 (n=3) | 5.732 ± 0.089 (n=3) | 5.271 ± 0.190 (n=3) | 5.517 ± 0.051 (n=3) |
| memoria | 1 | 0.958 ± 0.009 (n=3) | 0.963 ± 0.000 (n=3) | 0.948 ± 0.002 (n=3) | 0.951 ± 0.009 (n=3) |
| memoria | 2 | 1.926 ± 0.005 (n=3) | 1.925 ± 0.001 (n=3) | 1.903 ± 0.021 (n=3) | 1.902 ± 0.019 (n=3) |
| memoria | 3 | 2.908 ± 0.034 (n=3) | 2.887 ± 0.002 (n=3) | 2.853 ± 0.028 (n=3) | 2.836 ± 0.000 (n=3) |

### latencia_media_ms — ms

| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |
|---|---:|---|---|---|---|
| cpu | 1 | 258.137 ± 3.252 (n=3) | 259.031 ± 2.531 (n=3) | 235.036 ± 4.767 (n=3) | 232.075 ± 1.416 (n=3) |
| cpu | 2 | 519.568 ± 10.959 (n=3) | 518.636 ± 2.455 (n=3) | 235.890 ± 2.040 (n=3) | 235.000 ± 2.602 (n=3) |
| cpu | 5 | 1297.564 ± 38.951 (n=3) | 1398.591 ± 115.184 (n=3) | 648.312 ± 7.227 (n=3) | 651.042 ± 11.414 (n=3) |
| cpu | 10 | 2474.828 ± 4.233 (n=3) | 2793.502 ± 90.393 (n=3) | 1478.468 ± 81.483 (n=3) | 1450.999 ± 16.050 (n=3) |
| io | 1 | 186.188 ± 3.224 (n=3) | 182.940 ± 1.201 (n=3) | 190.856 ± 3.162 (n=3) | 198.479 ± 1.217 (n=3) |
| io | 2 | 352.757 ± 9.943 (n=3) | 346.923 ± 5.973 (n=3) | 376.365 ± 13.884 (n=3) | 360.303 ± 3.356 (n=3) |
| memoria | 1 | 1033.407 ± 11.496 (n=3) | 1026.511 ± 0.064 (n=3) | 1042.763 ± 6.542 (n=3) | 1041.748 ± 5.958 (n=3) |
| memoria | 2 | 1030.764 ± 1.481 (n=3) | 1028.318 ± 1.435 (n=3) | 1035.834 ± 1.941 (n=3) | 1039.699 ± 8.233 (n=3) |
| memoria | 3 | 1028.936 ± 0.467 (n=3) | 1030.351 ± 1.351 (n=3) | 1038.760 ± 3.179 (n=3) | 1041.266 ± 3.304 (n=3) |

### p95_ms — ms

| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |
|---|---:|---|---|---|---|
| cpu | 1 | 277.973 ± 8.550 (n=3) | 272.068 ± 3.608 (n=3) | 246.032 ± 8.383 (n=3) | 238.276 ± 2.409 (n=3) |
| cpu | 2 | 561.046 ± 14.851 (n=3) | 553.588 ± 4.495 (n=3) | 242.429 ± 4.441 (n=3) | 244.967 ± 10.848 (n=3) |
| cpu | 5 | 1421.501 ± 55.091 (n=3) | 1711.460 ± 258.841 (n=3) | 1182.615 ± 103.554 (n=3) | 1144.029 ± 63.907 (n=3) |
| cpu | 10 | 2975.555 ± 82.968 (n=3) | 3465.453 ± 136.894 (n=3) | 2626.153 ± 206.640 (n=3) | 2629.291 ± 47.190 (n=3) |
| io | 1 | 258.214 ± 7.936 (n=3) | 256.253 ± 4.133 (n=3) | 267.716 ± 7.607 (n=3) | 286.137 ± 5.390 (n=3) |
| io | 2 | 438.938 ± 6.976 (n=3) | 438.264 ± 24.531 (n=3) | 511.206 ± 62.282 (n=3) | 462.960 ± 21.726 (n=3) |
| memoria | 1 | 1031.801 ± 2.023 (n=3) | 1029.912 ± 0.776 (n=3) | 1102.014 ± 46.899 (n=3) | 1116.630 ± 50.114 (n=3) |
| memoria | 2 | 1046.243 ± 1.484 (n=3) | 1037.859 ± 5.199 (n=3) | 1077.871 ± 15.861 (n=3) | 1091.065 ± 40.433 (n=3) |
| memoria | 3 | 1041.196 ± 7.756 (n=3) | 1056.055 ± 5.814 (n=3) | 1082.338 ± 11.037 (n=3) | 1100.560 ± 25.086 (n=3) |

### falhas — requisições

| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |
|---|---:|---|---|---|---|
| cpu | 1 | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) |
| cpu | 2 | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) |
| cpu | 5 | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) |
| cpu | 10 | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) |
| io | 1 | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) |
| io | 2 | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) |
| memoria | 1 | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) |
| memoria | 2 | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) |
| memoria | 3 | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) | 0.000 ± 0.000 (n=3) |

### cpu_arvore_pct — % capacidade VM

| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |
|---|---:|---|---|---|---|
| cpu | 1 | 98.407 ± 0.074 (n=3) | 98.520 ± 0.027 (n=3) | 49.393 ± 0.077 (n=3) | 49.298 ± 0.020 (n=3) |
| cpu | 2 | 98.686 ± 0.103 (n=3) | 98.750 ± 0.027 (n=3) | 96.466 ± 0.444 (n=3) | 96.287 ± 1.030 (n=3) |
| cpu | 5 | 98.758 ± 0.075 (n=3) | 98.589 ± 0.240 (n=3) | 87.392 ± 1.103 (n=3) | 87.085 ± 1.483 (n=3) |
| cpu | 10 | 98.868 ± 0.019 (n=3) | 98.597 ± 0.061 (n=3) | 78.994 ± 1.384 (n=3) | 78.746 ± 0.840 (n=3) |
| io | 1 | 12.006 ± 0.223 (n=3) | 11.885 ± 0.140 (n=3) | 6.018 ± 0.016 (n=3) | 5.485 ± 0.047 (n=3) |
| io | 2 | 11.374 ± 0.331 (n=3) | 12.839 ± 0.611 (n=3) | 6.516 ± 0.659 (n=3) | 6.999 ± 0.269 (n=3) |
| memoria | 1 | 2.569 ± 0.069 (n=3) | 2.486 ± 0.044 (n=3) | 1.357 ± 0.010 (n=3) | 1.251 ± 0.012 (n=3) |
| memoria | 2 | 5.115 ± 0.194 (n=3) | 4.791 ± 0.010 (n=3) | 2.454 ± 0.088 (n=3) | 2.491 ± 0.117 (n=3) |
| memoria | 3 | 7.246 ± 0.145 (n=3) | 7.444 ± 0.168 (n=3) | 3.712 ± 0.154 (n=3) | 3.597 ± 0.013 (n=3) |

### cpu_global_pct — % capacidade VM; diagnóstico

| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |
|---|---:|---|---|---|---|
| cpu | 1 | 99.799 ± 0.030 (n=3) | 99.838 ± 0.033 (n=3) | 35.271 ± 4.791 (n=3) | 35.597 ± 3.143 (n=3) |
| cpu | 2 | 100.000 ± 0.000 (n=3) | 100.000 ± 0.000 (n=3) | 94.355 ± 0.728 (n=3) | 94.497 ± 2.182 (n=3) |
| cpu | 5 | 100.000 ± 0.000 (n=3) | 100.000 ± 0.000 (n=3) | 74.744 ± 2.750 (n=3) | 74.616 ± 3.573 (n=3) |
| cpu | 10 | 100.000 ± 0.000 (n=3) | 100.000 ± 0.000 (n=3) | 60.139 ± 2.139 (n=3) | 59.955 ± 1.394 (n=3) |
| io | 1 | 14.602 ± 0.213 (n=3) | 14.450 ± 0.236 (n=3) | 7.153 ± 0.110 (n=3) | 6.860 ± 0.021 (n=3) |
| io | 2 | 14.713 ± 0.341 (n=3) | 16.116 ± 0.854 (n=3) | 7.784 ± 0.538 (n=3) | 8.491 ± 0.414 (n=3) |
| memoria | 1 | 1.620 ± 0.130 (n=3) | 1.765 ± 0.084 (n=3) | 1.257 ± 0.127 (n=3) | 1.222 ± 0.019 (n=3) |
| memoria | 2 | 3.328 ± 0.144 (n=3) | 3.247 ± 0.025 (n=3) | 2.183 ± 0.219 (n=3) | 2.328 ± 0.141 (n=3) |
| memoria | 3 | 4.832 ± 0.196 (n=3) | 5.106 ± 0.329 (n=3) | 3.102 ± 0.299 (n=3) | 3.012 ± 0.192 (n=3) |

### ram_vm_mib — MiB

| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |
|---|---:|---|---|---|---|
| cpu | 1 | 430.979 ± 4.510 (n=3) | 439.576 ± 4.473 (n=3) | 585.733 ± 6.403 (n=3) | 629.101 ± 5.478 (n=3) |
| cpu | 2 | 436.273 ± 0.604 (n=3) | 444.858 ± 0.477 (n=3) | 589.088 ± 1.904 (n=3) | 630.007 ± 3.254 (n=3) |
| cpu | 5 | 437.482 ± 0.862 (n=3) | 445.393 ± 0.309 (n=3) | 588.387 ± 1.905 (n=3) | 631.173 ± 4.560 (n=3) |
| cpu | 10 | 438.249 ± 0.506 (n=3) | 446.578 ± 0.716 (n=3) | 585.178 ± 5.485 (n=3) | 634.944 ± 1.282 (n=3) |
| io | 1 | 427.592 ± 0.204 (n=3) | 435.620 ± 1.320 (n=3) | 578.635 ± 2.897 (n=3) | 620.453 ± 1.319 (n=3) |
| io | 2 | 419.135 ± 0.538 (n=3) | 427.410 ± 0.445 (n=3) | 576.485 ± 0.294 (n=3) | 615.484 ± 0.458 (n=3) |
| memoria | 1 | 463.260 ± 0.048 (n=3) | 471.131 ± 0.148 (n=3) | 625.631 ± 3.082 (n=3) | 652.582 ± 1.710 (n=3) |
| memoria | 2 | 512.818 ± 0.521 (n=3) | 520.328 ± 0.303 (n=3) | 669.238 ± 3.469 (n=3) | 703.375 ± 3.881 (n=3) |
| memoria | 3 | 563.559 ± 0.379 (n=3) | 571.108 ± 0.182 (n=3) | 709.991 ± 1.599 (n=3) | 750.575 ± 1.351 (n=3) |

### ram_disponivel_mib — MiB

| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |
|---|---:|---|---|---|---|
| cpu | 1 | 540.306 ± 4.510 (n=3) | 1538.209 ± 4.473 (n=3) | 385.310 ± 6.403 (n=3) | 1348.442 ± 5.478 (n=3) |
| cpu | 2 | 535.012 ± 0.604 (n=3) | 1532.927 ± 0.477 (n=3) | 381.955 ± 1.904 (n=3) | 1347.536 ± 3.254 (n=3) |
| cpu | 5 | 533.803 ± 0.862 (n=3) | 1532.392 ± 0.309 (n=3) | 382.656 ± 1.905 (n=3) | 1346.370 ± 4.560 (n=3) |
| cpu | 10 | 533.037 ± 0.506 (n=3) | 1531.207 ± 0.716 (n=3) | 385.865 ± 5.485 (n=3) | 1342.599 ± 1.282 (n=3) |
| io | 1 | 543.693 ± 0.204 (n=3) | 1542.165 ± 1.320 (n=3) | 392.408 ± 2.897 (n=3) | 1357.090 ± 1.319 (n=3) |
| io | 2 | 552.151 ± 0.538 (n=3) | 1550.376 ± 0.445 (n=3) | 394.558 ± 0.294 (n=3) | 1362.059 ± 0.458 (n=3) |
| memoria | 1 | 508.025 ± 0.048 (n=3) | 1506.654 ± 0.148 (n=3) | 345.412 ± 3.082 (n=3) | 1324.961 ± 1.710 (n=3) |
| memoria | 2 | 458.467 ± 0.521 (n=3) | 1457.457 ± 0.303 (n=3) | 301.805 ± 3.469 (n=3) | 1274.168 ± 3.881 (n=3) |
| memoria | 3 | 407.726 ± 0.379 (n=3) | 1406.677 ± 0.182 (n=3) | 261.052 ± 1.599 (n=3) | 1226.968 ± 1.351 (n=3) |

### rss_arvore_mib — MiB; soma RSS

| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |
|---|---:|---|---|---|---|
| cpu | 1 | 43.156 ± 0.000 (n=3) | 42.852 ± 0.000 (n=3) | 119.792 ± 0.165 (n=3) | 119.473 ± 0.000 (n=3) |
| cpu | 2 | 43.479 ± 0.056 (n=3) | 43.315 ± 0.141 (n=3) | 120.621 ± 0.081 (n=3) | 120.484 ± 0.059 (n=3) |
| cpu | 5 | 43.818 ± 0.044 (n=3) | 43.703 ± 0.036 (n=3) | 121.311 ± 0.048 (n=3) | 121.120 ± 0.041 (n=3) |
| cpu | 10 | 44.226 ± 0.146 (n=3) | 44.177 ± 0.160 (n=3) | 121.684 ± 0.428 (n=3) | 121.748 ± 0.034 (n=3) |
| io | 1 | 43.203 ± 0.149 (n=3) | 43.223 ± 0.149 (n=3) | 120.238 ± 0.149 (n=3) | 121.645 ± 0.074 (n=3) |
| io | 2 | 43.678 ± 0.313 (n=3) | 43.694 ± 0.311 (n=3) | 120.796 ± 0.397 (n=3) | 121.956 ± 0.232 (n=3) |
| memoria | 1 | 91.808 ± 0.336 (n=3) | 92.818 ± 0.435 (n=3) | 168.056 ± 0.669 (n=3) | 169.983 ± 0.386 (n=3) |
| memoria | 2 | 141.896 ± 0.457 (n=3) | 140.985 ± 0.392 (n=3) | 218.446 ± 0.678 (n=3) | 218.643 ± 1.188 (n=3) |
| memoria | 3 | 191.215 ± 0.924 (n=3) | 191.798 ± 1.154 (n=3) | 261.262 ± 2.045 (n=3) | 268.447 ± 0.498 (n=3) |

### rss_pico_mib — MiB; pico amostrado da soma RSS

| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |
|---|---:|---|---|---|---|
| cpu | 1 | 43.156 ± 0.000 (n=3) | 42.852 ± 0.000 (n=3) | 119.792 ± 0.165 (n=3) | 119.473 ± 0.000 (n=3) |
| cpu | 2 | 43.479 ± 0.056 (n=3) | 43.315 ± 0.141 (n=3) | 120.669 ± 0.065 (n=3) | 120.510 ± 0.016 (n=3) |
| cpu | 5 | 43.818 ± 0.044 (n=3) | 43.703 ± 0.036 (n=3) | 121.318 ± 0.038 (n=3) | 121.132 ± 0.022 (n=3) |
| cpu | 10 | 44.297 ± 0.159 (n=3) | 44.177 ± 0.160 (n=3) | 121.758 ± 0.359 (n=3) | 121.839 ± 0.134 (n=3) |
| io | 1 | 43.203 ± 0.149 (n=3) | 43.223 ± 0.149 (n=3) | 120.238 ± 0.149 (n=3) | 121.688 ± 0.000 (n=3) |
| io | 2 | 43.678 ± 0.313 (n=3) | 43.694 ± 0.311 (n=3) | 120.876 ± 0.261 (n=3) | 121.956 ± 0.232 (n=3) |
| memoria | 1 | 92.958 ± 0.174 (n=3) | 93.176 ± 0.000 (n=3) | 169.574 ± 0.179 (n=3) | 170.773 ± 0.000 (n=3) |
| memoria | 2 | 142.917 ± 0.073 (n=3) | 143.290 ± 0.072 (n=3) | 220.029 ± 0.109 (n=3) | 220.527 ± 0.000 (n=3) |
| memoria | 3 | 192.898 ± 0.139 (n=3) | 193.113 ± 0.000 (n=3) | 264.878 ± 0.309 (n=3) | 270.285 ± 0.000 (n=3) |

### uss_arvore_mib — MiB; soma USS

| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |
|---|---:|---|---|---|---|
| cpu | 1 | ausente (n=0) | ausente (n=0) | ausente (n=0) | ausente (n=0) |
| cpu | 2 | ausente (n=0) | ausente (n=0) | ausente (n=0) | ausente (n=0) |
| cpu | 5 | ausente (n=0) | ausente (n=0) | ausente (n=0) | ausente (n=0) |
| cpu | 10 | ausente (n=0) | ausente (n=0) | ausente (n=0) | ausente (n=0) |
| io | 1 | 30.342 ± 0.048 (n=3) | 30.249 ± 0.041 (n=3) | 78.622 ± 0.062 (n=3) | 79.477 ± 0.033 (n=3) |
| io | 2 | 30.706 ± 0.019 (n=3) | 30.616 ± 0.024 (n=3) | 79.412 ± 0.166 (n=3) | 79.546 ± 0.009 (n=3) |
| memoria | 1 | 78.912 ± 0.382 (n=3) | 79.691 ± 0.477 (n=3) | 126.736 ± 0.546 (n=3) | 128.521 ± 0.391 (n=3) |
| memoria | 2 | 129.165 ± 0.461 (n=3) | 127.827 ± 0.432 (n=3) | 177.000 ± 0.702 (n=3) | 177.155 ± 1.630 (n=3) |
| memoria | 3 | 178.653 ± 0.813 (n=3) | 178.986 ± 1.155 (n=3) | 220.164 ± 2.140 (n=3) | 227.647 ± 0.496 (n=3) |

### pss_arvore_mib — MiB; soma PSS

| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |
|---|---:|---|---|---|---|
| cpu | 1 | ausente (n=0) | ausente (n=0) | ausente (n=0) | ausente (n=0) |
| cpu | 2 | ausente (n=0) | ausente (n=0) | ausente (n=0) | ausente (n=0) |
| cpu | 5 | ausente (n=0) | ausente (n=0) | ausente (n=0) | ausente (n=0) |
| cpu | 10 | ausente (n=0) | ausente (n=0) | ausente (n=0) | ausente (n=0) |
| io | 1 | 33.133 ± 0.050 (n=3) | 33.061 ± 0.047 (n=3) | 82.292 ± 0.061 (n=3) | 82.888 ± 0.032 (n=3) |
| io | 2 | 33.504 ± 0.020 (n=3) | 33.435 ± 0.029 (n=3) | 83.082 ± 0.165 (n=3) | 82.955 ± 0.008 (n=3) |
| memoria | 1 | 81.616 ± 0.377 (n=3) | 82.528 ± 0.478 (n=3) | 130.481 ± 0.546 (n=3) | 131.854 ± 0.392 (n=3) |
| memoria | 2 | 131.872 ± 0.459 (n=3) | 130.689 ± 0.428 (n=3) | 180.755 ± 0.695 (n=3) | 180.490 ± 1.631 (n=3) |
| memoria | 3 | 181.363 ± 0.807 (n=3) | 181.848 ± 1.151 (n=3) | 223.923 ± 2.137 (n=3) | 230.983 ± 0.499 (n=3) |

### escrita_mib_s — MiB/s; dispositivo VM

| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |
|---|---:|---|---|---|---|
| io | 1 | 53.888 ± 1.088 (n=3) | 54.790 ± 0.422 (n=3) | 52.511 ± 0.642 (n=3) | 50.488 ± 0.301 (n=3) |
| io | 2 | 56.709 ± 1.519 (n=3) | 57.748 ± 1.031 (n=3) | 53.104 ± 2.009 (n=3) | 55.484 ± 0.503 (n=3) |

### escrita_total_mib — MiB; dispositivo VM

| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |
|---|---:|---|---|---|---|
| io | 1 | 3125.536 ± 63.064 (n=3) | 3177.727 ± 24.504 (n=3) | 3045.180 ± 36.692 (n=3) | 2928.380 ± 17.543 (n=3) |
| io | 2 | 3289.094 ± 88.136 (n=3) | 3349.184 ± 59.918 (n=3) | 3080.154 ± 116.680 (n=3) | 3217.283 ± 29.700 (n=3) |

### escritas_operacoes — operações; dispositivo VM

| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |
|---|---:|---|---|---|---|
| io | 1 | 6950.667 ± 138.583 (n=3) | 7050.667 ± 54.684 (n=3) | 6345.333 ± 190.437 (n=3) | 6254.667 ± 30.925 (n=3) |
| io | 2 | 7309.000 ± 187.745 (n=3) | 7428.333 ± 137.827 (n=3) | 5272.667 ± 222.588 (n=3) | 6195.667 ± 130.542 (n=3) |

### disco_ocupado_ms — ms; dispositivo VM

| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |
|---|---:|---|---|---|---|
| io | 1 | 55496.000 ± 259.446 (n=3) | 55550.667 ± 214.861 (n=3) | 54297.333 ± 431.487 (n=3) | 54932.000 ± 72.774 (n=3) |
| io | 2 | 55942.667 ± 211.105 (n=3) | 55264.000 ± 394.989 (n=3) | 55369.333 ± 276.155 (n=3) | 55529.333 ± 316.008 (n=3) |

## Pares de provisionamento

C1→C2 e C3→C4 associam o aumento de RAM a resultados mantendo vCPUs/workers constantes. C1→C3 e C2→C4 mudam vCPUs e workers conjuntamente, com RAM constante; não isolam efeitos de cada fator.

### C1 → C2: aumento de RAM

| Aplicação | Usuários | Δ vazão (req/s) | Δ vazão (%) | Δ latência (ms) | Δ latência (%) |
|---|---:|---:|---:|---:|---:|
| cpu | 1 | -0.016 | -0.405 | 0.894 | 0.346 |
| cpu | 2 | 0.009 | 0.233 | -0.932 | -0.179 |
| cpu | 5 | -0.271 | -7.099 | 101.027 | 7.786 |
| cpu | 10 | -0.485 | -12.217 | 318.673 | 12.877 |
| memoria | 1 | 0.005 | 0.541 | -6.895 | -0.667 |
| memoria | 2 | -0.001 | -0.060 | -2.446 | -0.237 |
| memoria | 3 | -0.021 | -0.723 | 1.415 | 0.137 |
| io | 1 | 0.086 | 1.616 | -3.248 | -1.745 |
| io | 2 | 0.097 | 1.726 | -5.834 | -1.654 |

### C3 → C4: aumento de RAM

| Aplicação | Usuários | Δ vazão (req/s) | Δ vazão (%) | Δ latência (ms) | Δ latência (%) |
|---|---:|---:|---:|---:|---:|
| cpu | 1 | 0.051 | 1.207 | -2.961 | -1.260 |
| cpu | 2 | 0.035 | 0.413 | -0.890 | -0.377 |
| cpu | 5 | -0.033 | -0.438 | 2.730 | 0.421 |
| cpu | 10 | 0.096 | 1.442 | -27.469 | -1.858 |
| memoria | 1 | 0.003 | 0.333 | -1.015 | -0.097 |
| memoria | 2 | -0.001 | -0.029 | 3.865 | 0.373 |
| memoria | 3 | -0.017 | -0.596 | 2.506 | 0.241 |
| io | 1 | -0.197 | -3.775 | 7.624 | 3.995 |
| io | 2 | 0.246 | 4.671 | -16.062 | -4.268 |

### C1 → C3: mudança conjunta de vCPUs e workers

| Aplicação | Usuários | Δ vazão (req/s) | Δ vazão (%) | Δ latência (ms) | Δ latência (%) |
|---|---:|---:|---:|---:|---:|
| cpu | 1 | 0.380 | 9.870 | -23.102 | -8.949 |
| cpu | 2 | 4.609 | 120.705 | -283.678 | -54.599 |
| cpu | 5 | 3.819 | 99.944 | -649.251 | -50.036 |
| cpu | 10 | 2.704 | 68.137 | -996.361 | -40.260 |
| memoria | 1 | -0.010 | -1.013 | 9.356 | 0.905 |
| memoria | 2 | -0.023 | -1.196 | 5.070 | 0.492 |
| memoria | 3 | -0.055 | -1.900 | 9.824 | 0.955 |
| io | 1 | -0.133 | -2.483 | 4.668 | 2.507 |
| io | 2 | -0.364 | -6.455 | 23.608 | 6.692 |

### C2 → C4: mudança conjunta de vCPUs e workers

| Aplicação | Usuários | Δ vazão (req/s) | Δ vazão (%) | Δ latência (ms) | Δ latência (%) |
|---|---:|---:|---:|---:|---:|
| cpu | 1 | 0.447 | 11.648 | -26.956 | -10.407 |
| cpu | 2 | 4.635 | 121.100 | -283.636 | -54.689 |
| cpu | 5 | 4.057 | 114.281 | -747.549 | -53.450 |
| cpu | 10 | 3.285 | 94.301 | -1342.502 | -48.058 |
| memoria | 1 | -0.012 | -1.218 | 15.236 | 1.484 |
| memoria | 2 | -0.022 | -1.165 | 11.381 | 1.107 |
| memoria | 3 | -0.051 | -1.775 | 10.915 | 1.059 |
| io | 1 | -0.416 | -7.656 | 15.540 | 8.495 |
| io | 2 | -0.215 | -3.746 | 13.380 | 3.857 |

## Interpretação dos padrões observados

### CPU e saturação

- C1: vazão de 3.851 req/s (1 usuário), 3.818 (2) e 3.968 (10). CPU da árvore com 2 usuários: 98.686% da capacidade; latência média de 258.137 para 2474.828 ms entre 1 e 10 usuários.
- C2: vazão de 3.835 req/s (1 usuário), 3.827 (2) e 3.484 (10). CPU da árvore com 2 usuários: 98.750% da capacidade; latência média de 259.031 para 2793.502 ms entre 1 e 10 usuários.
- C3: vazão de 4.231 req/s (1 usuário), 8.428 (2) e 6.672 (10). CPU da árvore com 2 usuários: 96.466% da capacidade; latência média de 235.036 para 1478.468 ms entre 1 e 10 usuários.
- C4: vazão de 4.282 req/s (1 usuário), 8.462 (2) e 6.769 (10). CPU da árvore com 2 usuários: 96.287% da capacidade; latência média de 232.075 para 1450.999 ms entre 1 e 10 usuários.

CPU próxima da capacidade, vazão que deixa de crescer e latência crescente são compatíveis com saturação e formação de filas. Nos cenários de duas vCPUs, observe também a queda de utilização/vazão nas maiores demandas: esses dados não isolam mecanismos de agendamento ou sobrecarga. A mudança conjunta de workers e vCPUs impede atribuir o ganho somente ao processador. CPU normalizada de 100% em C1/C2 representa uma vCPU, em C3/C4 duas; percentuais iguais não equivalem a tempo de CPU absoluto igual. CPU global está nas tabelas separadamente; inconsistências conhecidas dos contadores globais impedem reconciliá-la automaticamente com a árvore.

### Memória

- C1: na aplicação memória, RSS de 91.808 para 191.215 MiB entre 1 e 3 usuários; vazão de 0.958 para 2.908 req/s.
- C2: na aplicação memória, RSS de 92.818 para 191.798 MiB entre 1 e 3 usuários; vazão de 0.963 para 2.887 req/s.
- C3: na aplicação memória, RSS de 168.056 para 261.262 MiB entre 1 e 3 usuários; vazão de 0.948 para 2.853 req/s.
- C4: na aplicação memória, RSS de 169.983 para 268.447 MiB entre 1 e 3 usuários; vazão de 0.951 para 2.836 req/s.

Soma RSS inclui páginas compartilhadas e não mede memória privada. USS/PSS disponíveis complementam a interpretação; aumentar workers pode aumentar o consumo base dos processos. RAM usada é do sistema inteiro. O nome Memory-bound descreve o perfil da API; estes resumos não comprovam saturação de largura de banda de RAM nem ausência/presença de swap. A retenção temporal pode dominar a latência e não deve ser interpretada como tempo de acesso à memória; seus parâmetros não podem ser revalidados exclusivamente pelos agregados. Não há melhora de RAM universal a presumir nos pares.

### I/O

- C1: vazão I/O de 5.343 para 5.635 req/s entre 1 e 2 usuários; latência de 186.188 para 352.757 ms; escrita média com 2 usuários: 56.709 MiB/s.
- C2: vazão I/O de 5.429 para 5.732 req/s entre 1 e 2 usuários; latência de 182.940 para 346.923 ms; escrita média com 2 usuários: 57.748 MiB/s.
- C3: vazão I/O de 5.210 para 5.271 req/s entre 1 e 2 usuários; latência de 190.856 para 376.365 ms; escrita média com 2 usuários: 53.104 MiB/s.
- C4: vazão I/O de 5.014 para 5.517 req/s entre 1 e 2 usuários; latência de 198.479 para 360.303 ms; escrita média com 2 usuários: 55.484 MiB/s.

Contadores de disco referem-se somente a `sda`, nunca à soma disco+partição. Ganhos limitados de vazão com maior latência e baixa CPU são compatíveis com espera de I/O, mas não demonstram saturação física do armazenamento do Windows. O dispositivo é da VM inteira; cache, fsync e a camada de disco virtual influenciam resultados. Bytes de arquivos e bytes do dispositivo não são intercambiáveis; nenhum contador é atribuído integralmente à API.

## Limitações metodológicas

- Houve uma atualização do Ubuntu durante a campanha, conforme o contexto do experimento. As fontes não contêm data/versão suficientes para quantificar seu efeito; ele permanece possível fator de confusão.
- Tentativas inválidas foram recuperadas em novas execuções físicas. Mudanças de horário, sistema e instrumentação podem influenciar a comparação; os agregados não contêm a sequência completa dessas recuperações.
- São três repetições independentes por combinação conforme a coleta declarada. Os CSVs agregados permitem verificar contagens/resumos, mas não auditar identidades, independência real ou seleção de tentativas novamente.
- Offset e incerteza dos relógios e as janelas UTC não constam nesses CSVs. Nenhuma nova sincronização é presumida, nenhum alinhamento é refeito e nenhum aviso anterior de CPU global é considerado resolvido.
- Parâmetros das APIs, ordem de coleta, versões, retenção e fsync não podem ser conferidos nessas fontes. A comparabilidade pressupõe o protocolo declarado; não foi comprovada novamente por acesso a outras fontes.
- DP descreve variabilidade entre repetições; sobreposição ou separação das barras não constitui teste de significância. Ausências/contagens parciais são explícitas; nenhuma imputação foi realizada.

## Conclusões

Os números observados permitem comparar desempenho e variabilidade no protocolo adotado. O padrão CPU diferencia capacidade sob concorrência; RSS caracteriza custo de memória com demanda; I/O exige considerar espera, sincronização e virtualização. As tabelas de diferenças registram tanto ganhos quanto perdas, sem concluir benefício causal universal do aumento de RAM ou isolar vCPUs de workers. A atualização do sistema e as recuperações limitam conclusões causais definitivas.

## Gráficos

### cpu: vazao

![cpu vazao](cpu_vazao.png)

### cpu: latencia

![cpu latencia](cpu_latencia.png)

### cpu: cpu

![cpu cpu](cpu_cpu.png)

### cpu: memoria

![cpu memoria](cpu_memoria.png)

### cpu: falhas

![cpu falhas](cpu_falhas.png)

### memoria: vazao

![memoria vazao](memoria_vazao.png)

### memoria: latencia

![memoria latencia](memoria_latencia.png)

### memoria: cpu

![memoria cpu](memoria_cpu.png)

### memoria: memoria

![memoria memoria](memoria_memoria.png)

### memoria: falhas

![memoria falhas](memoria_falhas.png)

### io: vazao

![io vazao](io_vazao.png)

### io: latencia

![io latencia](io_latencia.png)

### io: cpu

![io cpu](io_cpu.png)

### io: memoria

![io memoria](io_memoria.png)

### io: falhas

![io falhas](io_falhas.png)

### io: disco

![io disco](io_disco.png)
