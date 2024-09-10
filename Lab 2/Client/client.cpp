#include <sys/types.h>
#include <unistd.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netdb.h>

#define SERVER_PORT 8080 /* Porta do servidor */
#define BUFSIZE 4096     /* Tamanho do buffer de transferência */

int main(int argc, char **argv)
{
    int c, s, bytes;
    char buf[BUFSIZE];      /* Buffer para receber o arquivo */
    char command[BUFSIZE];  /* Buffer para o comando do terminal */
    int client_port = 0;    /* Porta de origem do cliente (opcional) */

    struct hostent *h;          /* Info sobre o servidor */
    struct sockaddr_in client_addr, server_addr; /* Endereços do cliente e do servidor */
    socklen_t len = sizeof(client_addr); /* Para obter a porta usada localmente */

    /* Verificar se o usuário forneceu servidor e, opcionalmente, uma porta */
    if (argc != 2 && argc != 3)
    {
        printf("Uso: client <server-name> [client-port]\n");
        exit(-1);
    }

    /* Se uma porta de origem for passada, converta para inteiro */
    if (argc == 3)
    {
        client_port = atoi(argv[2]);
        if (client_port <= 0 || client_port > 65535)
        {
            printf("Porta inválida fornecida. Use um número entre 1 e 65535.\n");
            exit(-1);
        }
    }

    h = gethostbyname(argv[1]); /* Buscar o IP do servidor */
    if (!h)
    {
        printf("gethostbyname falhou ao localizar %s", argv[1]);
        exit(-1);
    }

    /* Criar o socket */
    s = socket(PF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s < 0)
    {
        printf("Falha ao criar o socket\n");
        exit(-1);
    }

    /* Definir o endereço do cliente */
    memset(&client_addr, 0, sizeof(client_addr));
    client_addr.sin_family = AF_INET;
    client_addr.sin_addr.s_addr = htonl(INADDR_ANY); /* Permite que o sistema escolha o IP */
    if (client_port > 0)
    {
        client_addr.sin_port = htons(client_port); /* Usar a porta fornecida pelo cliente */
        /* Ligar o socket à porta especificada */
        if (bind(s, (struct sockaddr *)&client_addr, sizeof(client_addr)) < 0)
        {
            printf("Falha ao bindar na porta %d\n", client_port);
            exit(-1);
        }
    }

    /* Definir o endereço do servidor */
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    memcpy(&server_addr.sin_addr.s_addr, h->h_addr, h->h_length);
    server_addr.sin_port = htons(SERVER_PORT); /* Porta do servidor */

    /* Conectar ao servidor */
    c = connect(s, (struct sockaddr *)&server_addr, sizeof(server_addr));
    if (c < 0)
    {
        printf("Falha ao conectar ao servidor\n");
        exit(-1);
    }

    /* Pega a porta local usada */
    if (getsockname(s, (struct sockaddr *)&client_addr, &len) == -1) {
        perror("getsockname");
        exit(-1);
    }

    printf("Conectado a %s:%d. Insira os comandos:\n", argv[1], ntohs(client_addr.sin_port));
    printf("Comandos válidos:\n");
    printf("  MyGet <arquivo>\n");
    printf("  MyLastAccess\n");
    printf("  exit()\n\n");

    /* Loop principal para manter o cliente ativo */
    while (1)
    {
        printf("\033[0;36m> \033[0;37m"); /* Prompt azul */
        fgets(command, BUFSIZE, stdin); /* Receber o comando do terminal */
        command[strcspn(command, "\n")] = 0; /* Remover o caractere de nova linha */

        /* Verificar se o comando é válido */
        if (strncmp(command, "MyGet ", 6) == 0)
        {
            /* Enviar o comando para o servidor */
            write(s, command, strlen(command) + 1);

            /* Ler a resposta do servidor e imprimir o conteúdo do arquivo */
            while ((bytes = read(s, buf, BUFSIZE)) > 0)
            {
                write(1, buf, bytes); /* Escrever na saída padrão */
                if (bytes < BUFSIZE)
                { /* Se ler menos que o BUFSIZE, significa que é o fim da resposta */
                    break;
                }
            }
        }
        else if (strcmp(command, "MyLastAccess") == 0)
        {
            /* Enviar o comando MyLastAccess para o servidor */
            write(s, command, strlen(command) + 1);

            /* Ler a resposta do servidor e imprimir */
            while ((bytes = read(s, buf, BUFSIZE)) > 0)
            {
                write(1, buf, bytes); /* Escrever na saída padrão */
                if (bytes < BUFSIZE)
                {
                    break;
                }
            }
        }
        else if (strcmp(command, "exit()") == 0)
        {
            /* Fechar a conexão e sair */
            printf("\nFechando conexão...\n");
            close(s);
            exit(0);
        }
        else
        {
            printf("Comando inválido\n");
        }

        /* Limpar os buffers para a próxima iteração */
        memset(buf, 0, BUFSIZE);
        memset(command, 0, BUFSIZE);
    }

    return 0;
}
