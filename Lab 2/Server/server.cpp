/* This is the server code */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <sys/fcntl.h>
#include <netdb.h>
#include <sys/types.h>
#include <pthread.h>
#include <arpa/inet.h> // Para conversão de endereços IP
#include <stdarg.h>    // Para usar va_start e va_end
#include <time.h>

#define SERVER_PORT 8080 /* arbitrary, but client & server must agree */
#define BUF_SIZE 4096    /* block transfer size */
#define QUEUE_SIZE 10    /* max number of waiting clients */
#define MAX_COLORS 6     /* Número de cores disponíveis */

// Definição de cores
const char *colors[MAX_COLORS] = {
    "\033[1;31m",  // Vermelho
    "\033[1;32m",  // Verde
    "\033[1;33m",  // Amarelo
    "\033[1;34m",  // Azul
    "\033[1;35m",  // Magenta
    "\033[1;36m"   // Ciano
};

const char *reset_color = "\033[0m"; // Reseta para cor padrão

typedef struct
{
   int socket;
   struct sockaddr_in client_addr;
   time_t last_access;
   const char *color; // Cor atribuída ao cliente
} ClientData;

typedef struct
{
   char client_ip_port[INET_ADDRSTRLEN + 6]; // Para armazenar "IP:porta"
   time_t last_access;
   const char *color; // Cor atribuída ao cliente no histórico
} ClientHistory;

ClientHistory client_histories[100]; // Armazena histórico de até 100 clientes
int history_count = 0;               // Contador de clientes no histórico

// Função para procurar o histórico de um cliente pelo IP:porta
int find_client_history(const char *client_ip_port)
{
   for (int i = 0; i < history_count; i++)
   {
      if (strcmp(client_histories[i].client_ip_port, client_ip_port) == 0)
      {
         return i; // Retorna o índice do histórico
      }
   }
   return -1; // Cliente não encontrado
}

// Função para atualizar ou adicionar o histórico de um cliente
void update_client_history(const char *client_ip_port, time_t last_access, const char *color)
{
   int index = find_client_history(client_ip_port);
   if (index >= 0)
   {
      client_histories[index].last_access = last_access; // Atualiza o último acesso
   }
   else if (history_count < 100)
   {
      // Adiciona novo cliente ao histórico
      strcpy(client_histories[history_count].client_ip_port, client_ip_port);
      client_histories[history_count].last_access = last_access;
      client_histories[history_count].color = color; // Atribui uma cor ao cliente
      history_count++;
   }
}

// Função para exibir IP:porta do cliente com cor
void print_colored_ip_port(const char *color, const char *client_ip_port) {
    printf("%s(%s)%s ", color, client_ip_port, reset_color);
}

/* Função que será chamada em uma nova thread para lidar com cada cliente */
void *handle_client(void *arg)
{
   ClientData *client_data = (ClientData *)arg;
   int sa = client_data->socket; /* socket do cliente */
   char buf[BUF_SIZE];           /* buffer para receber comandos e enviar dados */
   int fd, bytes;

   /* Converte o endereço IP do cliente e a porta para string legível */
   char client_ip[INET_ADDRSTRLEN];
   inet_ntop(AF_INET, &(client_data->client_addr.sin_addr), client_ip, INET_ADDRSTRLEN);
   int client_port = ntohs(client_data->client_addr.sin_port);

   // Construir string "IP:porta"
   char client_ip_port[INET_ADDRSTRLEN + 6]; // Espaço para "IP:porta"
   snprintf(client_ip_port, sizeof(client_ip_port), "%s:%d", client_ip, client_port);

   // Tenta encontrar o último acesso do cliente no histórico
   int history_index = find_client_history(client_ip_port);
   if (history_index >= 0)
   {
      client_data->last_access = client_histories[history_index].last_access;
      client_data->color = client_histories[history_index].color; // Usa a mesma cor do histórico
   }
   else
   {
      client_data->last_access = 0; // Primeiro acesso do cliente
   }

   // Mensagem de cliente conectado
   print_colored_ip_port(client_data->color, client_ip_port);
   printf("Client connected.\n");

   while (1)
   { // Loop contínuo para receber múltiplos comandos do mesmo cliente
      /* Lê o comando enviado pelo cliente */
      bytes = read(sa, buf, BUF_SIZE);
      if (bytes <= 0)
      {
         print_colored_ip_port(client_data->color, client_ip_port);
         printf("Connection closed.\n");
         break; // Se o cliente fechar a conexão ou ocorrer erro, sair do loop
      }

      buf[bytes] = '\0';  // Assegura que o buffer é uma string com final '\0'
      print_colored_ip_port(client_data->color, client_ip_port);
      printf("Received command: %s\n", buf);  // Exibe o comando recebido

      /* Verifica se o comando é "MyGet" */
      if (strncmp(buf, "MyGet ", 6) == 0)
      {
         char *file_name = buf + 6;  // Obtém o nome do arquivo após "MyGet "
         print_colored_ip_port(client_data->color, client_ip_port);
         printf("Requested file: %s\n", file_name);

         /* Abre o arquivo solicitado */
         fd = open(file_name, O_RDONLY);
         if (fd < 0)
         {
            // Arquivo não encontrado, envia erro para o cliente
            snprintf(buf, BUF_SIZE, "Error: File not found\n");
            write(sa, buf, strlen(buf));  // Envia mensagem de erro para o cliente
         }
         else
         {
            // Lê e envia o conteúdo do arquivo ao cliente
            while ((bytes = read(fd, buf, BUF_SIZE)) > 0)
            {
               write(sa, buf, bytes);  // Escreve o arquivo para o socket
            }
            close(fd);  // Fecha o arquivo após enviar tudo
         }
      }
      /* Verifica se o comando é "MyLastAccess" */
      else if (strcmp(buf, "MyLastAccess") == 0)
      {
         char last_access_str[BUF_SIZE];
         if (client_data->last_access == 0)
         {
            snprintf(last_access_str, BUF_SIZE, "Last Access=Null\n");
         }
         else
         {
            struct tm *lt = localtime(&client_data->last_access);
            strftime(last_access_str, sizeof(last_access_str), "Last Access=%Y-%m-%d %H:%M:%S\n", lt);
         }
         write(sa, last_access_str, strlen(last_access_str));  // Envia o último acesso
      }
      /* Verifica se o comando é "exit()" */
      else if (strcmp(buf, "exit()") == 0)
      {
         print_colored_ip_port(client_data->color, client_ip_port);
         printf("Requested to close the connection.\n");
         break;  // O cliente solicitou fechar a conexão
      }
      /* Comando inválido */
      else
      {
         snprintf(buf, BUF_SIZE, "Error: Invalid command\n");
         write(sa, buf, strlen(buf));  // Informa ao cliente que o comando é inválido
      }

      /* Atualiza o último acesso do cliente após o envio da resposta */
      time(&client_data->last_access);  // Atualiza o horário do último acesso
      update_client_history(client_ip_port, client_data->last_access, client_data->color);  // Atualiza o histórico do cliente
   }

   /* Fecha a conexão e libera a memória alocada para o cliente */
   close(sa);
   free(client_data);
   return NULL;
}

// Função para printar o array de históricos de clientes a cada 5 segundos
void *print_client_histories(void *arg) {
    while (1) {
        sleep(10); // Espera 5 segundos
        printf("\n\n------- Client Histories -------\n");
        for (int i = 0; i < history_count; i++) {
            printf("Client %s, Last Access: %ld\n",
                   client_histories[i].client_ip_port,
                   client_histories[i].last_access);
        }
        printf("--------------------------------\n\n");
    }
}

int main(int argc, char *argv[])
{
   int s, b, l, sa, on = 1;
   char buf[BUF_SIZE];  // Buffer for outgoing file

   struct sockaddr_in channel;     // Endereço do servidor
   struct sockaddr_in client_addr; // Endereço do cliente

   pthread_t thread, print_thread;
   socklen_t client_len = sizeof(client_addr);  // Tamanho do endereço do cliente

   /* Build address structure to bind to socket. */
   memset(&channel, 0, sizeof(channel));

   /* Zero channel */
   channel.sin_family = AF_INET;
   channel.sin_addr.s_addr = htonl(INADDR_ANY);
   channel.sin_port = htons(SERVER_PORT);

   /* Passive open. Wait for connection. */
   s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);  // Create socket
   if (s < 0)
   {
      printf("Socket call failed");
      exit(-1);
   }

   setsockopt(s, SOL_SOCKET, SO_REUSEADDR, (char *)&on, sizeof(on));

   b = bind(s, (struct sockaddr *)&channel, sizeof(channel));
   if (b < 0)
   {
      printf("Bind failed");
      exit(-1);
   }

   l = listen(s, QUEUE_SIZE);  // Specify queue size
   if (l < 0)
   {
      printf("Listen failed");
      exit(-1);
   }
   printf("Server is listening on port %d\n", SERVER_PORT);

   // Criar thread para printar os históricos de clientes a cada 5 segundos
   pthread_create(&print_thread, NULL, print_client_histories, NULL);

   /* Socket is now set up and bound. Wait for connection and process it. */
   while (1)
   {
      sa = accept(s, (struct sockaddr *)&client_addr, &client_len);  // Aceita nova conexão
      if (sa < 0)
      {
         printf("Accept failed");
         continue;  // Continua no loop em caso de falha na conexão
      }

      /* Aloca dados para o cliente e inicia uma nova thread para processá-lo */
      ClientData *client_data = (ClientData *)malloc(sizeof(ClientData));  // Alocação de memória para o cliente
      client_data->socket = sa;
      client_data->client_addr = client_addr;
      client_data->last_access = 0;

      // Atribui uma cor ao cliente, reutilizando a cor se ele já tiver um histórico
      char client_ip_port[INET_ADDRSTRLEN + 6];
      snprintf(client_ip_port, sizeof(client_ip_port), "%s:%d", inet_ntoa(client_addr.sin_addr), ntohs(client_addr.sin_port));

      int history_index = find_client_history(client_ip_port);
      if (history_index >= 0)
      {
         client_data->color = client_histories[history_index].color;  // Usa a cor existente
      }
      else
      {
         client_data->color = colors[history_count % MAX_COLORS];  // Atribui uma cor nova
      }

      pthread_create(&thread, NULL, handle_client, client_data);  // Cria thread
      pthread_detach(thread);                                     // Permite que a thread libere seus recursos automaticamente
   }

   close(s);  // Fecha o socket principal
   return 0;
}
