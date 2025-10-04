"""
Unified messaging API endpoints for all users
"""
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
import logging

from database.connection import get_db
from database.models import User, ProfessorStudentMessage, Cohort
from database.schemas import (
    MessageCreate, 
    MessageReply, 
    MessageResponse, 
    MessageListResponse,
    MessageThreadResponse
)
from utilities.auth import get_current_user
from services.notification_service import create_professor_message_notification, create_student_reply_notification, create_message_sent_notification, notification_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/messages", tags=["messages"])

@router.post("/", response_model=MessageResponse)
async def send_message(
    message_data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a message to any user"""
    
    # Verify the recipient exists
    recipient = db.query(User).filter(User.id == message_data.recipient_id).first()
    
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient not found"
        )
    
    # If cohort_id is provided, verify it exists
    cohort = None
    if message_data.cohort_id:
        cohort = db.query(Cohort).filter(Cohort.id == message_data.cohort_id).first()
        if not cohort:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cohort not found"
            )
    
    # Create the message - handle both professor->student and student->professor
    if current_user.role == 'professor':
        message = ProfessorStudentMessage(
            professor_id=current_user.id,
            student_id=recipient.id,
            cohort_id=message_data.cohort_id,
            subject=message_data.subject,
            message=message_data.message,
            message_type=message_data.message_type,
            professor_read=True,  # Sender always reads their own message
            student_read=False    # Recipient hasn't read it yet
        )
    else:  # Student sending to professor
        message = ProfessorStudentMessage(
            professor_id=recipient.id,
            student_id=current_user.id,
            cohort_id=message_data.cohort_id,
            subject=message_data.subject,
            message=message_data.message,
            message_type=message_data.message_type,
            professor_read=False,  # Recipient hasn't read it yet
            student_read=True      # Sender always reads their own message
        )
    
    db.add(message)
    db.commit()
    db.refresh(message)
    
    # Create notification for the recipient
    if current_user.role == 'professor' and recipient.role == 'student':
        create_professor_message_notification(
            db=db,
            professor=current_user,
            student=recipient,
            message_subject=message_data.subject,
            cohort_id=message_data.cohort_id
        )
    elif current_user.role == 'student' and recipient.role == 'professor':
        # For new messages from students to professors, use a different notification type
        notification_service.create_notification(
            db=db,
            user_id=recipient.id,
            notification_type='student_message',
            variables={
                'student_name': current_user.full_name,
                'message_subject': message_data.subject
            },
            data={
                'student_id': current_user.id,
                'cohort_id': message_data.cohort_id,
                'message_type': 'student_message'
            }
        )
    
    # Create sent message notification for the sender
    create_message_sent_notification(
        db=db,
        sender=current_user,
        recipient=recipient,
        message_subject=message_data.subject,
        cohort_id=message_data.cohort_id
    )
    
    # Return the message with relationships
    return MessageResponse(
        id=message.id,
        professor_id=message.professor_id,
        student_id=message.student_id,
        cohort_id=message.cohort_id,
        subject=message.subject,
        message=message.message,
        message_type=message.message_type,
        parent_message_id=message.parent_message_id,
        is_reply=message.is_reply,
        professor_read=message.professor_read,
        student_read=message.student_read,
        created_at=message.created_at,
        updated_at=message.updated_at,
        professor={
            "id": current_user.id,
            "full_name": current_user.full_name,
            "email": current_user.email
        },
        student={
            "id": recipient.id,
            "full_name": recipient.full_name,
            "email": recipient.email
        },
        cohort={
            "id": cohort.id,
            "title": cohort.title,
            "course_code": cohort.course_code
        } if cohort else None,
        replies=[]
    )

@router.get("/", response_model=List[MessageListResponse])
async def get_messages(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get messages for the current user"""
    
    # Get messages where user is either sender or recipient
    messages = db.query(ProfessorStudentMessage).options(
        joinedload(ProfessorStudentMessage.professor),
        joinedload(ProfessorStudentMessage.student),
        joinedload(ProfessorStudentMessage.cohort)
    ).filter(
        (ProfessorStudentMessage.professor_id == current_user.id) |
        (ProfessorStudentMessage.student_id == current_user.id)
    ).order_by(ProfessorStudentMessage.created_at.desc()).offset(offset).limit(limit).all()
    
    result = []
    for message in messages:
        # Get reply count
        reply_count = db.query(ProfessorStudentMessage).filter(
            ProfessorStudentMessage.parent_message_id == message.id
        ).count()
        
        result.append(MessageListResponse(
            id=message.id,
            professor_id=message.professor_id,
            student_id=message.student_id,
            cohort_id=message.cohort_id,
            subject=message.subject,
            message=message.message,
            message_type=message.message_type,
            parent_message_id=message.parent_message_id,
            is_reply=message.is_reply,
            professor_read=message.professor_read,
            student_read=message.student_read,
            created_at=message.created_at,
            updated_at=message.updated_at,
            professor={
                "id": message.professor.id,
                "full_name": message.professor.full_name,
                "email": message.professor.email
            } if message.professor else None,
            student={
                "id": message.student.id,
                "full_name": message.student.full_name,
                "email": message.student.email
            } if message.student else None,
            cohort={
                "id": message.cohort.id,
                "title": message.cohort.title,
                "course_code": message.cohort.course_code
            } if message.cohort else None,
            reply_count=reply_count
        ))
    
    return result

@router.get("/{message_id}", response_model=MessageThreadResponse)
async def get_message_thread(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a message thread with replies"""
    
    # Get the parent message
    parent_message = db.query(ProfessorStudentMessage).filter(
        ProfessorStudentMessage.id == message_id,
        (ProfessorStudentMessage.professor_id == current_user.id) |
        (ProfessorStudentMessage.student_id == current_user.id)
    ).first()
    
    if not parent_message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Get all replies
    replies = db.query(ProfessorStudentMessage).filter(
        ProfessorStudentMessage.parent_message_id == message_id
    ).order_by(ProfessorStudentMessage.created_at.asc()).all()
    
    # Convert replies to response format
    reply_responses = []
    for reply in replies:
        reply_responses.append(MessageResponse(
            id=reply.id,
            professor_id=reply.professor_id,
            student_id=reply.student_id,
            cohort_id=reply.cohort_id,
            subject=reply.subject,
            message=reply.message,
            message_type=reply.message_type,
            parent_message_id=reply.parent_message_id,
            is_reply=reply.is_reply,
            professor_read=reply.professor_read,
            student_read=reply.student_read,
            created_at=reply.created_at,
            updated_at=reply.updated_at,
            professor={
                "id": reply.professor.id,
                "full_name": reply.professor.full_name,
                "email": reply.professor.email
            } if reply.professor else None,
            student={
                "id": reply.student.id,
                "full_name": reply.student.full_name,
                "email": reply.student.email
            } if reply.student else None,
            cohort={
                "id": reply.cohort.id,
                "title": reply.cohort.title,
                "course_code": reply.cohort.course_code
            } if reply.cohort else None,
            replies=[]
        ))
    
    # Convert parent message to response format
    parent_response = MessageResponse(
        id=parent_message.id,
        professor_id=parent_message.professor_id,
        student_id=parent_message.student_id,
        cohort_id=parent_message.cohort_id,
        subject=parent_message.subject,
        message=parent_message.message,
        message_type=parent_message.message_type,
        parent_message_id=parent_message.parent_message_id,
        is_reply=parent_message.is_reply,
        professor_read=parent_message.professor_read,
        student_read=parent_message.student_read,
        created_at=parent_message.created_at,
        updated_at=parent_message.updated_at,
        professor={
            "id": parent_message.professor.id,
            "full_name": parent_message.professor.full_name,
            "email": parent_message.professor.email
        } if parent_message.professor else None,
        student={
            "id": parent_message.student.id,
            "full_name": parent_message.student.full_name,
            "email": parent_message.student.email
        } if parent_message.student else None,
        cohort={
            "id": parent_message.cohort.id,
            "title": parent_message.cohort.title,
            "course_code": parent_message.cohort.course_code
        } if parent_message.cohort else None,
        replies=reply_responses
    )
    
    return MessageThreadResponse(
        parent_message=parent_response,
        replies=reply_responses
    )

@router.post("/{message_id}/reply", response_model=MessageResponse)
async def reply_to_message(
    message_id: int,
    reply_data: MessageReply,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reply to a message"""
    
    # Get the parent message
    parent_message = db.query(ProfessorStudentMessage).filter(
        ProfessorStudentMessage.id == message_id,
        (ProfessorStudentMessage.professor_id == current_user.id) |
        (ProfessorStudentMessage.student_id == current_user.id)
    ).first()
    
    if not parent_message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Determine the recipient (opposite of current user)
    recipient_id = parent_message.student_id if current_user.id == parent_message.professor_id else parent_message.professor_id
    
    # Create the reply
    reply = ProfessorStudentMessage(
        professor_id=current_user.id if current_user.role == 'professor' else parent_message.professor_id,
        student_id=current_user.id if current_user.role == 'student' else parent_message.student_id,
        cohort_id=parent_message.cohort_id,
        subject=f"Re: {parent_message.subject}",
        message=reply_data.message,
        message_type=parent_message.message_type,
        parent_message_id=message_id,
        is_reply=True,
        professor_read=current_user.role == 'professor',
        student_read=current_user.role == 'student'
    )
    
    db.add(reply)
    db.commit()
    db.refresh(reply)
    
    # Create notification for the recipient
    recipient = db.query(User).filter(User.id == recipient_id).first()
    if recipient:
        if current_user.role == 'student' and recipient.role == 'professor':
            create_student_reply_notification(
                db=db,
                student=current_user,
                professor=recipient,
                message_subject=parent_message.subject,
                cohort_id=parent_message.cohort_id
            )
        elif current_user.role == 'professor' and recipient.role == 'student':
            create_professor_message_notification(
                db=db,
                professor=current_user,
                student=recipient,
                message_subject=parent_message.subject,
                cohort_id=parent_message.cohort_id
            )
    
    # Return the reply
    return MessageResponse(
        id=reply.id,
        professor_id=reply.professor_id,
        student_id=reply.student_id,
        cohort_id=reply.cohort_id,
        subject=reply.subject,
        message=reply.message,
        message_type=reply.message_type,
        parent_message_id=reply.parent_message_id,
        is_reply=reply.is_reply,
        professor_read=reply.professor_read,
        student_read=reply.student_read,
        created_at=reply.created_at,
        updated_at=reply.updated_at,
        professor={
            "id": reply.professor.id,
            "full_name": reply.professor.full_name,
            "email": reply.professor.email
        } if reply.professor else None,
        student={
            "id": reply.student.id,
            "full_name": reply.student.full_name,
            "email": reply.student.email
        } if reply.student else None,
        cohort={
            "id": reply.cohort.id,
            "title": reply.cohort.title,
            "course_code": reply.cohort.course_code
        } if reply.cohort else None,
        replies=[]
    )

@router.post("/{message_id}/mark-read")
async def mark_message_read(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a message as read"""
    
    message = db.query(ProfessorStudentMessage).filter(
        ProfessorStudentMessage.id == message_id,
        (ProfessorStudentMessage.professor_id == current_user.id) |
        (ProfessorStudentMessage.student_id == current_user.id)
    ).first()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Update read status based on user role
    if current_user.role == 'professor':
        message.professor_read = True
    else:
        message.student_read = True
    
    db.commit()
    
    return {"message": "Message marked as read"}

@router.get("/users/", response_model=List[dict])
async def get_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all users for messaging"""
    
    users = db.query(User).filter(User.id != current_user.id).all()
    
    return [
        {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role
        }
        for user in users
    ]

@router.get("/cohorts/", response_model=List[dict])
async def get_cohorts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all cohorts for messaging"""
    
    cohorts = db.query(Cohort).all()
    
    return [
        {
            "id": cohort.id,
            "title": cohort.title,
            "course_code": cohort.course_code
        }
        for cohort in cohorts
    ]
