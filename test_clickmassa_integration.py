#!/usr/bin/env python3
"""
Script para testar a integração ClickMassa CRM
Testa:
1. Autenticação com token
2. Busca de mensagens com direção (fromMe)
3. Notas internas vs mensagens diretas
"""
import asyncio
import sys
sys.path.insert(0, "/app/backend")

from tools import execute_clickmassa_tool, get_clickmassa_token
import json


async def test_clickmassa():
    print("=" * 80)
    print("TESTE DE INTEGRAÇÃO CLICKMASSA CRM")
    print("=" * 80)
    
    # Credenciais (simulando o que vem do banco)
    credentials = {
        "workspace_id": "ws_test",
        "base_url": "https://enterprise-40api.clickmassa.com.br",
        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZW5hbnRJZCI6MjcsInByb2ZpbGUiOiJhZG1pbiIsInNlc3Npb25JZCI6MzUsImNoYW5uZWxUeXBlIjoid2hhdHNhcHAiLCJpYXQiOjE3NzU3NjQxMjIsImV4cCI6MTgzODgzNjEyMn0.EyN35FhFf6YjSHtlCofUWmSLJ8QEhSfcVX7szySk8CQ",
        "canal_id": "1"
    }
    
    # Test 1: Verificar token
    print("\n[TEST 1] Verificando autenticação com token...")
    try:
        token = await get_clickmassa_token(credentials)
        print(f"✅ Token obtido com sucesso: {token[:20]}...")
    except Exception as e:
        print(f"❌ Erro ao obter token: {e}")
        return
    
    # Test 2: Listar tickets abertos (verifica direção de mensagens)
    print("\n[TEST 2] Listando tickets abertos (verifica direção das mensagens)...")
    try:
        result = await execute_clickmassa_tool("listar_tickets_abertos", {}, credentials)
        if "error" in result:
            print(f"❌ Erro: {result['error']}")
        else:
            tickets = result.get("tickets", [])
            print(f"✅ Encontrados {len(tickets)} tickets abertos")
            if tickets:
                # Mostra primeiro ticket com lastMessage
                ticket = tickets[0]
                print(f"\n  📋 Ticket #{ticket.get('id')}:")
                print(f"     Contato: {ticket.get('contact', {}).get('name', 'N/A')}")
                print(f"     Status: {ticket.get('status', 'N/A')}")
                last_msg = ticket.get('lastMessage', {})
                if last_msg:
                    print(f"     Última mensagem:")
                    print(f"       - Direção: {last_msg.get('direcao', 'N/A')}")
                    print(f"       - fromMe: {last_msg.get('fromMe', 'N/A')}")
                    print(f"       - Texto: {last_msg.get('body', '')[:60]}...")
                print(f"\n  ℹ️  Instrução retornada: {result.get('instrucao_direcao', 'N/A')[:100]}...")
    except Exception as e:
        print(f"❌ Erro: {e}")
    
    # Test 2b: Listar contatos
    print("\n[TEST 2b] Listando contatos...")
    try:
        result = await execute_clickmassa_tool("listar_contatos", {}, credentials)
        if "error" in result:
            print(f"❌ Erro: {result['error']}")
        else:
            contacts = result.get("contacts", result if isinstance(result, list) else [])
            print(f"✅ Encontrados {len(contacts)} contatos")
            if contacts:
                contact = contacts[0]
                print(f"  📇 Primeiro contato:")
                print(f"     Nome: {contact.get('name', 'N/A')}")
                print(f"     Número: {contact.get('number', 'N/A')}")
    except Exception as e:
        print(f"❌ Erro: {e}")
    
    # Test 3: Buscar mensagens de um ticket (se houver algum)
    print("\n[TEST 3] Buscando mensagens completas de um ticket...")
    try:
        # Primeiro pega um ticket para testar
        tickets_result = await execute_clickmassa_tool("listar_tickets_abertos", {}, credentials)
        tickets = tickets_result.get("tickets", [])
        if tickets:
            ticket_id = tickets[0]["id"]
            print(f"  Usando ticket_id: {ticket_id}")
            
            result = await execute_clickmassa_tool(
                "buscar_mensagens_ticket",
                {"ticket_id": str(ticket_id), "pagina": 1},
                credentials
            )
            
            if "error" in result:
                print(f"❌ Erro: {result['error']}")
            else:
                messages = result.get("mensagens", [])
                print(f"✅ Encontradas {len(messages)} mensagens")
                print(f"  ℹ️  Instrução: {result.get('instrucao', 'N/A')}")
                
                # Mostra primeiras 3 mensagens
                for i, msg in enumerate(messages[:3]):
                    print(f"\n  Mensagem {i+1}:")
                    print(f"    - Direção: {msg.get('direcao')}")
                    print(f"    - fromMe: {msg.get('fromMe')}")
                    print(f"    - Nota interna?: {msg.get('isNotaInterna')}")
                    print(f"    - Texto: {msg.get('texto', '')[:50]}...")
        else:
            print("  ⚠️  Nenhum ticket aberto para testar")
    except Exception as e:
        print(f"❌ Erro: {e}")
    
    # Test 4: Schema da ferramenta enviar_nota_interna
    print("\n[TEST 4] Verificando schema da ferramenta 'enviar_nota_interna'...")
    from tools import _make_tool_def
    nota_tool = _make_tool_def("clickmassa", "enviar_nota_interna", 
                                "Adiciona nota interna no ticket — INVISÍVEL para o lead")
    print(f"✅ Schema da ferramenta:")
    print(json.dumps(nota_tool, indent=2, ensure_ascii=False))
    
    print("\n" + "=" * 80)
    print("TESTES CONCLUÍDOS")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_clickmassa())
